"""
Ticker-Name-Resolver: $GME → "GameStop Corp."

Nutzt yfinance als primäre Quelle, AlphaVantage als Fallback.
Ergebnis wird 24h gecacht (Firmennamen ändern sich selten).
"""

from __future__ import annotations

import asyncio

import yfinance as yf
from loguru import logger

from wsb_crawler.storage.cache import name_cache


def _resolve_sync(ticker: str) -> str | None:
    """Synchroner yfinance-Call für Firmennamen."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("shortName") or info.get("longName") or None
    except Exception:
        return None


async def resolve_name(ticker: str) -> str | None:
    """
    Löst einen Ticker in einen Firmennamen auf.
    24h gecacht, gibt None zurück wenn unbekannt.
    """
    cached = name_cache.get(ticker)
    if cached is not None or name_cache.get(ticker) == "":
        return cached or None

    name = await asyncio.to_thread(_resolve_sync, ticker)
    name_cache.set(ticker, name or "")
    if name:
        logger.debug(f"Ticker aufgelöst: {ticker} → {name}")
    return name


async def resolve_names_bulk(tickers: list[str]) -> dict[str, str | None]:
    """Löst mehrere Ticker parallel auf."""
    results = await asyncio.gather(*[resolve_name(t) for t in tickers])
    return dict(zip(tickers, results))
