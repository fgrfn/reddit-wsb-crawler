"""
Kursdaten-Enrichment via yfinance.

yfinance selbst ist synchron, wir wrappen es in asyncio.to_thread()
damit es den Event-Loop nicht blockiert. Alle Ticker werden parallel
geholt (asyncio.gather).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from wsb_crawler.models import MarketStatus, PriceData
from wsb_crawler.storage.cache import price_cache


def _determine_market_status(info: dict) -> MarketStatus:
    """Bestimmt den aktuellen Marktstatus aus yfinance-Info."""
    market_state = info.get("marketState", "CLOSED").upper()
    if market_state == "PRE":
        return MarketStatus.PRE_MARKET
    if market_state in ("REGULAR", "OPEN"):
        return MarketStatus.OPEN
    if market_state in ("POST", "POSTPOST"):
        return MarketStatus.AFTER_HOURS
    return MarketStatus.CLOSED


def _safe_float(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
        return f if f == f else None   # NaN check
    except (TypeError, ValueError):
        return None


def _fetch_price_sync(ticker: str) -> PriceData:
    """Synchroner yfinance-Call (wird in Thread ausgeführt)."""
    stock = yf.Ticker(ticker)
    info = stock.info

    # Kursverlauf für 1h/24h/7d Berechnung
    hist_1d = stock.history(period="1d", interval="1h")
    hist_7d = stock.history(period="7d", interval="1d")

    current_price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))

    # Prozentuale Veränderungen berechnen
    change_1h = None
    change_24h = None
    change_7d = None

    if not hist_1d.empty and current_price:
        oldest_1h = _safe_float(hist_1d["Close"].iloc[0])
        if oldest_1h and oldest_1h > 0:
            change_1h = (current_price - oldest_1h) / oldest_1h * 100

    if not hist_1d.empty and current_price:
        open_price = _safe_float(hist_1d["Open"].iloc[0])
        if open_price and open_price > 0:
            change_24h = (current_price - open_price) / open_price * 100

    if not hist_7d.empty and len(hist_7d) >= 2 and current_price:
        week_open = _safe_float(hist_7d["Open"].iloc[0])
        if week_open and week_open > 0:
            change_7d = (current_price - week_open) / week_open * 100

    market_status = _determine_market_status(info)

    return PriceData(
        ticker=ticker,
        company_name=info.get("shortName") or info.get("longName"),
        price=current_price,
        currency=info.get("currency", "USD"),
        change_1h=change_1h,
        change_24h=change_24h,
        change_7d=change_7d,
        pre_market_price=_safe_float(info.get("preMarketPrice")),
        pre_market_change=_safe_float(info.get("preMarketChangePercent")),
        after_hours_price=_safe_float(info.get("postMarketPrice")),
        after_hours_change=_safe_float(info.get("postMarketChangePercent")),
        market_status=market_status,
        volume=int(info.get("volume", 0)) or None,
        market_cap=_safe_float(info.get("marketCap")),
        fetched_at=datetime.now(tz=timezone.utc),
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=False,
)
async def get_price(ticker: str) -> PriceData | None:
    """
    Holt den aktuellen Kurs für einen Ticker.
    Nutzt den Cache (5 Min TTL) um API-Calls zu minimieren.

    Bei Fehler: gibt None zurück (kein Crash des ganzen Runs).
    """
    cached = price_cache.get(ticker)
    if cached is not None:
        logger.debug(f"Cache-Hit für Kurs: {ticker}")
        return cached

    try:
        data = await asyncio.to_thread(_fetch_price_sync, ticker)
        price_cache.set(ticker, data)
        logger.debug(f"Kurs geholt: {ticker} = {data.primary_price} {data.currency}")
        return data
    except Exception as e:
        logger.warning(f"Konnte Kurs für {ticker} nicht holen: {e}")
        return None


async def get_prices_bulk(tickers: list[str]) -> dict[str, PriceData | None]:
    """
    Holt Kursdaten für mehrere Ticker gleichzeitig (parallel).
    Gibt {ticker: PriceData | None} zurück.
    """
    results = await asyncio.gather(*[get_price(t) for t in tickers])
    return dict(zip(tickers, results))
