"""
Trend-Analyse: berechnet Top-Mover und Verlaufs-Daten für Discord-Commands.

Nutzt die SQLite-History — ermöglicht Fragen wie:
"Welche Ticker sind in den letzten 7 Tagen am stärksten gestiegen?"
"""

from __future__ import annotations

import asyncio

from loguru import logger

from wsb_crawler.enrichment.prices import get_prices_bulk
from wsb_crawler.enrichment.resolver import resolve_names_bulk
from wsb_crawler.models import TickerHistory, TrendDirection, TrendEntry
from wsb_crawler.storage.database import Database


async def get_top_tickers(db: Database, days: int = 7, limit: int = 10) -> list[TrendEntry]:
    """
    Gibt die Top-Ticker der letzten N Tage zurück,
    angereichert mit Firmennamen und Kursdaten.
    """
    entries = await db.get_top_tickers(days=days, limit=limit)

    if not entries:
        return []

    tickers = [e.ticker for e in entries]

    # Namen + aktuelle Kurse parallel holen
    names, prices = await asyncio.gather(
        resolve_names_bulk(tickers),
        get_prices_bulk(tickers),
    )

    enriched: list[TrendEntry] = []
    for entry in entries:
        t = entry.ticker
        price = prices.get(t)
        history = await db.get_ticker_history(t, days=days)

        enriched.append(
            TrendEntry(
                ticker=t,
                company_name=names.get(t),
                total_mentions=entry.total_mentions,
                avg_daily_mentions=entry.avg_daily_mentions,
                peak_day=entry.peak_day,
                peak_mentions=entry.peak_mentions,
                trend_direction=_calculate_trend(history),
                current_price=price.primary_price if price else None,
                price_change_period=price.change_7d if price and days >= 7 else price.change_24h if price else None,
            )
        )

    logger.debug(f"Trend-Analyse: Top {len(enriched)} Ticker der letzten {days} Tage")
    return enriched


def _calculate_trend(history: TickerHistory) -> TrendDirection:
    """
    Berechnet die Trend-Richtung aus der Mention-History.

    Vergleicht die letzten 3 Tage mit den 4 Tagen davor.
    """
    counts = history.mention_counts
    if len(counts) < 4:
        return TrendDirection.FLAT

    recent_avg = sum(c for _, c in counts[-3:]) / 3
    older_avg = sum(c for _, c in counts[-7:-3]) / max(1, len(counts[-7:-3]))

    if older_avg == 0:
        return TrendDirection.UP if recent_avg > 0 else TrendDirection.FLAT

    delta_pct = (recent_avg - older_avg) / older_avg
    if delta_pct > 0.3:
        return TrendDirection.UP
    if delta_pct < -0.3:
        return TrendDirection.DOWN
    return TrendDirection.FLAT


async def get_ticker_chart_data(
    db: Database, ticker: str, days: int = 30
) -> TickerHistory:
    """Gibt die Mention-History für einen Ticker zurück (für /chart Command)."""
    return await db.get_ticker_history(ticker, days=days)
