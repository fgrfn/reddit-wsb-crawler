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
from wsb_crawler.storage.database import Database


async def analyze_mentions(
    mention_counts: dict[str, int],
    db: Database,
) -> list[Alert]:
    """
    Analysiert Ticker-Nennungen und gibt ausgelöste Alerts zurück.

    Ablauf:
    1. Für jeden Ticker: historischen Avg aus DB holen
    2. Spike-Check: ratio und delta berechnen
    3. Cooldown prüfen
    4. Für Alert-Kandidaten: Kurs + News parallel holen
    5. Alerts erstellen

    Gibt maximal alert_max_per_run Alerts zurück.
    """
    cfg = (await get_settings(db)).alerts
    alerts: list[Alert] = []

    if not mention_counts:
        return alerts

    # Kandidaten-Vorauswahl (ohne DB-Calls für Nicht-Kandidaten)
    spike_results: list[SpikeResult] = []

    for ticker, current in mention_counts.items():
        avg = await db.get_avg_mentions(ticker, days=30)
        is_new = not await db.is_known_ticker(ticker)

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

    # Nur Kandidaten weiter anreichern
    candidates = [s for s in spike_results if s.reason is not None]

    if not candidates:
        logger.debug("Keine Spike-Kandidaten in diesem Lauf")
        return alerts

    logger.info(f"{len(candidates)} Spike-Kandidat(en) gefunden: {[c.ticker for c in candidates]}")

    # Cooldown-Check (filtered aus Kandidaten)
    active_candidates: list[SpikeResult] = []
    for spike in candidates:
        if await db.is_on_cooldown(spike.ticker):
            logger.debug(f"{spike.ticker} im Cooldown – übersprungen")
            continue
        active_candidates.append(spike)

    if not active_candidates:
        logger.info("Alle Kandidaten im Cooldown")
        return alerts

    # Auf max_per_run begrenzen (nach Relevanz sortieren)
    active_candidates.sort(key=lambda s: s.ratio, reverse=True)
    active_candidates = active_candidates[: cfg.max_per_run]

    tickers_to_enrich = [s.ticker for s in active_candidates]

    # Kurs + News + Namen parallel holen
    prices, news_map, names = await asyncio.gather(
        get_prices_bulk(tickers_to_enrich),
        get_news_bulk(tickers_to_enrich),
        resolve_names_bulk(tickers_to_enrich),
    )

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

    return alerts
