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
from wsb_crawler.models import Alert, AlertReason, SpikeResult
from wsb_crawler.runtime.progress import update_run
from wsb_crawler.storage.database import Database


def _confidence_score(spike: SpikeResult) -> int:
    """Ein einfacher Erklärbarkeits-Score für Alert-Vorschau und Dashboard."""
    score = 30
    score += min(30, spike.current_mentions)
    if spike.is_new:
        score += 10
    if spike.ratio == float("inf"):
        score += 20
    else:
        score += min(20, int(spike.ratio * 4))
    if spike.price_data and spike.price_data.primary_change is not None:
        score += min(10, int(abs(spike.price_data.primary_change)))
    if spike.news:
        score += min(10, len(spike.news) * 2)
    return max(0, min(100, score))


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
            "price_change": alert.spike.price_data.primary_change if alert.spike.price_data else None,
            "news_count": len(alert.spike.news),
            "confidence": _confidence_score(alert.spike),
        }
        for alert in alerts
    ]


async def analyze_mentions(
    mention_counts: dict[str, int],
    db: Database,
    run_id: str | None = None,
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
            )
        )

        if idx % 25 == 0:
            update_run(
                message=f"Spike-Analyse: {idx}/{len(relevant_items)} relevante Ticker geprüft…",
                progress=62 + int((idx / max(1, len(relevant_items))) * 10),
            )

    # Nur Kandidaten weiter anreichern
    candidates = [s for s in spike_results if s.reason is not None]
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

    # Auf max_per_run begrenzen (nach Relevanz sortieren)
    active_candidates.sort(key=lambda s: s.ratio, reverse=True)
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
