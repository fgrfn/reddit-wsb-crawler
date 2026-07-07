"""
Spike-Detektor: erkennt ungewöhnliche Ticker-Aktivität.

Vergleicht aktuelle Mentions mit historischem Durchschnitt (30 Tage).
Berücksichtigt Cooldowns damit derselbe Ticker nicht spammt.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from wsb_crawler.config import get_settings
from wsb_crawler.enrichment.news import get_news_bulk
from wsb_crawler.enrichment.prices import get_prices_bulk
from wsb_crawler.enrichment.resolver import resolve_names_bulk
from wsb_crawler.models import Alert, AlertReason, SpikeResult, TickerSignal
from wsb_crawler.runtime.progress import add_diagnostic, update_run
from wsb_crawler.storage.database import Database

# Implizite 3-Buchstaben-Ticker sind die häufigste Restquelle für False Positives.
# Bekannte WSB-/Mega-Cap-Ticker dürfen normal durch. Unbekannte neue 3-Letter-
# Kandidaten brauchen mehr absolute Erwähnungen, bevor ein Discord-Alert entsteht.
HIGH_SIGNAL_SHORT_TICKERS = frozenset(
    {
        "AMD",
        "AMC",
        "ARM",
        "BBAI",
        "CRM",
        "GME",
        "IBM",
        "IONQ",
        "MARA",
        "NIO",
        "PLTR",
        "QQQ",
        "RIVN",
        "SMCI",
        "SOFI",
        "SPY",
        "TLRY",
        "TSM",
        "XOM",
    }
)


def _quality_allows_alert(spike: SpikeResult, *, min_abs: int) -> bool:
    """Filtert besonders riskante neue Kurz-Ticker vor dem Alert-Versand."""
    if spike.reason != AlertReason.NEW_TICKER:
        return True
    if len(spike.ticker) != 3:
        return True
    if spike.ticker in HIGH_SIGNAL_SHORT_TICKERS:
        return True
    return spike.current_mentions >= max(min_abs * 2, 50)


def _confidence_score(spike: SpikeResult) -> int:
    """
    Erklärbarkeits-Score (0..100) für Alert-Vorschau und Dashboard.

    Bündelt Volumen, Spike-Stärke, Engagement (Post-Scores), Sentiment-Klarheit,
    Kursbewegung und News-Deckung zu einem Wert.
    """
    score = 20  # Basis
    score += min(25, spike.current_mentions)  # Volumen
    if spike.is_new:
        score += 8
    if spike.ratio == float("inf"):
        score += 20  # Spike-Stärke
    else:
        score += min(18, int(spike.ratio * 4))
    if spike.signal:
        score += int(15 * spike.signal.engagement_weight)  # Upvote-Engagement
        score += min(8, int(abs(spike.signal.sentiment) * 8))  # klare Richtung
    if spike.price_data and spike.price_data.primary_change is not None:
        score += min(8, int(abs(spike.price_data.primary_change)))
    if spike.news:
        score += min(8, len(spike.news) * 2)
    return max(0, min(100, score))


def _candidate_rank(spike: SpikeResult) -> float:
    """
    Relevanz für die Auswahl bei mehr Kandidaten als max_per_run.

    Primär die Spike-Stärke (ratio), zusätzlich hochgewichtet nach Engagement
    und Volumen — so gewinnt eine Nennung in viralen Posts gegen eine gleich
    starke ratio in Randbeiträgen. Läuft vor der Enrichment (kein Kurs/News).
    """
    ratio = 100.0 if spike.ratio == float("inf") else min(spike.ratio, 100.0)
    engagement = spike.signal.engagement_weight if spike.signal else 0.0
    sentiment = abs(spike.signal.sentiment) if spike.signal else 0.0
    return ratio + engagement * 10 + sentiment * 5 + min(spike.current_mentions, 50) * 0.2


def _alert_preview(alerts: list[Alert]) -> list[dict[str, object]]:
    return [
        {
            "ticker": alert.ticker,
            "reason": alert.reason.value,
            "mentions": alert.spike.current_mentions,
            "avg_mentions": round(alert.spike.avg_mentions, 2),
            "ratio": None if alert.spike.ratio == float("inf") else round(alert.spike.ratio, 2),
            "delta": alert.spike.delta,
            "is_new": alert.spike.is_new,
            "price": alert.spike.price_data.primary_price if alert.spike.price_data else None,
            "price_change": alert.spike.price_data.primary_change
            if alert.spike.price_data
            else None,
            "news_count": len(alert.spike.news),
            "confidence": alert.spike.confidence or _confidence_score(alert.spike),
            "sentiment": round(alert.spike.signal.sentiment, 2) if alert.spike.signal else 0.0,
            "sentiment_label": (
                alert.spike.signal.sentiment_label if alert.spike.signal else "neutral"
            ),
            "avg_score": round(alert.spike.signal.avg_score, 1) if alert.spike.signal else 0.0,
        }
        for alert in alerts
    ]


async def analyze_mentions(
    mention_counts: dict[str, int],
    db: Database,
    run_id: str | None = None,
    signals: dict[str, TickerSignal] | None = None,
) -> list[Alert]:
    """
    Analysiert Ticker-Nennungen und gibt ausgelöste Alerts zurück.

    Ablauf:
    1. Für jeden Ticker: historischen Avg aus DB holen
    2. Spike-Check: ratio und delta berechnen
    3. Cooldown prüfen
    4. Für Alert-Kandidaten: Kurs + News parallel holen
    5. Alerts erstellen

    run_id: ID des aktuellen Laufs. Dessen Mentions sind beim Aufruf bereits
    gespeichert und müssen aus History-Queries ausgeschlossen werden — sonst
    ist jeder Ticker "bekannt" und NEW_TICKER-Alerts können nie auslösen.

    Gibt maximal alert_max_per_run Alerts zurück.
    """
    cfg = (await get_settings(db)).alerts
    alerts: list[Alert] = []
    signals = signals or {}

    if not mention_counts:
        update_run(
            phase="analysis",
            phase_label="Spikes analysieren",
            message="Keine Ticker-Nennungen für die Analyse gefunden.",
            progress=70,
            candidate_count=0,
            active_candidate_count=0,
            alert_preview=[],
        )
        return alerts

    # Vorfilter: jeder Alert-Typ erfordert mindestens min(min_abs, min_delta)
    # Nennungen — für das Gros der Ticker (1-2 Nennungen) sparen wir uns die DB-Calls
    min_relevant = min(cfg.min_abs, cfg.min_delta)
    relevant_items = [
        (ticker, current) for ticker, current in mention_counts.items() if current >= min_relevant
    ]
    spike_results: list[SpikeResult] = []

    update_run(
        phase="analysis",
        phase_label="Spikes analysieren",
        message=f"Prüfe {len(relevant_items)} relevante Ticker gegen die 30-Tage-Historie…",
        progress=62,
    )

    for idx, (ticker, current) in enumerate(relevant_items, start=1):
        avg = await db.get_avg_mentions(ticker, days=30, exclude_run_id=run_id)
        is_new = not await db.is_known_ticker(ticker, exclude_run_id=run_id)

        ratio = current / avg if avg > 0 else float("inf")
        delta = current - int(avg)

        # Spike-Bedingungen prüfen
        reason: AlertReason | None = None

        if is_new and current >= cfg.min_abs:
            reason = AlertReason.NEW_TICKER

        elif not is_new and delta >= cfg.min_delta and ratio >= cfg.ratio:
            reason = AlertReason.SPIKE

        spike_results.append(
            SpikeResult(
                ticker=ticker,
                current_mentions=current,
                avg_mentions=avg,
                ratio=ratio,
                delta=delta,
                is_new=is_new,
                reason=reason,
                signal=signals.get(ticker),
            )
        )

        if idx % 25 == 0:
            update_run(
                message=f"Spike-Analyse: {idx}/{len(relevant_items)} relevante Ticker geprüft…",
                progress=62 + int((idx / max(1, len(relevant_items))) * 10),
            )

    raw_candidates = [s for s in spike_results if s.reason is not None]
    candidates = [s for s in raw_candidates if _quality_allows_alert(s, min_abs=cfg.min_abs)]
    filtered_count = len(raw_candidates) - len(candidates)
    if filtered_count:
        add_diagnostic(
            "info",
            f"{filtered_count} unsichere neue Kurz-Ticker vor Alert-Versand gefiltert.",
            source="ticker-quality",
        )
    update_run(candidate_count=len(candidates))

    if not candidates:
        logger.debug("Keine Spike-Kandidaten in diesem Lauf")
        update_run(
            phase="analysis",
            phase_label="Spikes analysieren",
            message="Keine Spike-Kandidaten in diesem Lauf.",
            progress=78,
            active_candidate_count=0,
            alert_preview=[],
        )
        return alerts

    logger.info(f"{len(candidates)} Spike-Kandidat(en) gefunden: {[c.ticker for c in candidates]}")
    update_run(
        message=f"{len(candidates)} Spike-Kandidat(en) gefunden. Prüfe Cooldowns…",
        progress=74,
    )

    # Cooldown-Check (filtered aus Kandidaten)
    active_candidates: list[SpikeResult] = []
    for spike in candidates:
        if await db.is_on_cooldown(spike.ticker):
            logger.debug(f"{spike.ticker} im Cooldown – übersprungen")
            continue
        active_candidates.append(spike)

    update_run(active_candidate_count=len(active_candidates))

    if not active_candidates:
        logger.info("Alle Kandidaten im Cooldown")
        update_run(
            phase="analysis",
            phase_label="Spikes analysieren",
            message="Alle Kandidaten sind noch im Cooldown.",
            progress=80,
            alert_preview=[],
        )
        return alerts

    # Auf max_per_run begrenzen (nach Relevanz sortieren: Spike-Stärke +
    # Engagement + Volumen, damit virale Nennungen bei Gleichstand gewinnen)
    active_candidates.sort(key=_candidate_rank, reverse=True)
    active_candidates = active_candidates[: cfg.max_per_run]

    tickers_to_enrich = [s.ticker for s in active_candidates]
    update_run(
        phase="enrich",
        phase_label="Kurse & News",
        message=f"Hole Kurse, Namen und News für {', '.join(tickers_to_enrich)}…",
        progress=80,
        active_candidate_count=len(active_candidates),
    )

    # Kurs + Namen parallel holen, danach News mit Firmennamen
    # (die News-Suche findet mit "GameStop" deutlich mehr als nur mit "$GME")
    prices, names = await asyncio.gather(
        get_prices_bulk(tickers_to_enrich),
        resolve_names_bulk(tickers_to_enrich),
    )
    update_run(
        message="Kurse und Firmennamen geladen. Hole passende News…",
        progress=83,
    )
    news_map = await get_news_bulk(tickers_to_enrich, company_names=names)

    for spike in active_candidates:
        t = spike.ticker
        price_data = prices.get(t)
        spike.price_data = price_data
        spike.news = news_map.get(t, [])

        # Optionaler Kurs-Alert Check
        if (
            price_data
            and price_data.primary_change is not None
            and abs(price_data.primary_change) >= cfg.min_price_move
            and spike.reason == AlertReason.SPIKE
        ):
            spike.reason = AlertReason.PRICE_MOVE

        spike.confidence = _confidence_score(spike)
        alert = Alert(ticker=t, reason=spike.reason, spike=spike)  # type: ignore[arg-type]
        alerts.append(alert)

        logger.info(
            f"Alert: {t} | {spike.reason} | "
            f"{spike.current_mentions} Nennungen ({spike.ratio:.1f}x Avg)"
        )

    update_run(
        phase="enrich",
        phase_label="Kurse & News",
        message=f"{len(alerts)} Alert(s) vorbereitet.",
        progress=85,
        alert_preview=_alert_preview(alerts),
    )
    return alerts
