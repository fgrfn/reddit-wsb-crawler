"""
Kursdaten-Enrichment via yfinance.

yfinance selbst ist synchron, wir wrappen es in asyncio.to_thread(),
drosseln die Zugriffe aber bewusst. Yahoo antwortet bei parallelen/retry-starken
QuoteSummary-Anfragen schnell mit 429 Too Many Requests.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import yfinance as yf
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from wsb_crawler.models import MarketStatus, PriceData
from wsb_crawler.storage.cache import price_cache

# Yahoo/yfinance mag keine Burst-Anfragen. Selbst bei nur wenigen Alert-Kandidaten
# erzeugt yfinance intern mehrere Requests pro Ticker. Daher: sequenziell + kurze
# Pause + negative Cache-Einträge, damit Fehlschläge nicht im selben Run mehrfach
# retried werden.
YFINANCE_MAX_ATTEMPTS = 2
YFINANCE_REQUEST_DELAY_SECONDS = 1.5
_failed_price_cache: set[str] = set()
_price_lock = asyncio.Lock()


def _determine_market_status(info: dict[str, Any]) -> MarketStatus:
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
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def _fetch_price_sync(ticker: str) -> PriceData:
    """Synchroner yfinance-Call (wird in Thread ausgeführt)."""
    stock = yf.Ticker(ticker)
    info = stock.fast_info

    # Kursverlauf für 1h/24h/7d Berechnung. fast_info vermeidet den besonders
    # rate-limit-anfälligen quoteSummary/info-Endpunkt für Basisdaten.
    hist_1d = stock.history(period="1d", interval="1h")
    hist_7d = stock.history(period="7d", interval="1d")

    current_price = _safe_float(info.get("last_price") or info.get("regular_market_price"))

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

    volume_f = _safe_float(info.get("last_volume"))
    volume = int(volume_f) if volume_f else None

    return PriceData(
        ticker=ticker,
        company_name=None,
        price=current_price,
        currency=info.get("currency", "USD"),
        change_1h=change_1h,
        change_24h=change_24h,
        change_7d=change_7d,
        pre_market_price=None,
        pre_market_change=None,
        after_hours_price=None,
        after_hours_change=None,
        market_status=MarketStatus.CLOSED,
        volume=volume,
        market_cap=_safe_float(info.get("market_cap")),
        fetched_at=datetime.now(tz=UTC),
    )


@retry(
    stop=stop_after_attempt(YFINANCE_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=2, min=3, max=15),
    reraise=True,
)
async def _fetch_price_with_retry(ticker: str) -> PriceData:
    """Kurs mit wenigen Versuchen holen.

    Muss Exceptions durchreichen, damit tenacity überhaupt retryen kann.
    """
    async with _price_lock:
        await asyncio.sleep(YFINANCE_REQUEST_DELAY_SECONDS)
        return await asyncio.to_thread(_fetch_price_sync, ticker)


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

    if ticker in _failed_price_cache:
        logger.debug(f"Negativer Cache-Hit für Kurs: {ticker}")
        return None

    try:
        data: PriceData = await _fetch_price_with_retry(ticker)
        price_cache.set(ticker, data)
        logger.debug(f"Kurs geholt: {ticker} = {data.primary_price} {data.currency}")
        return data
    except Exception as e:
        _failed_price_cache.add(ticker)
        logger.warning(f"Konnte Kurs für {ticker} nicht holen: {e}")
        return None


async def get_prices_bulk(tickers: list[str]) -> dict[str, PriceData | None]:
    """
    Holt Kursdaten für mehrere Ticker gedrosselt.
    Gibt {ticker: PriceData | None} zurück.
    """
    unique_tickers = list(dict.fromkeys(tickers))
    results: dict[str, PriceData | None] = {}
    for ticker in unique_tickers:
        results[ticker] = await get_price(ticker)
    return {ticker: results.get(ticker) for ticker in tickers}
