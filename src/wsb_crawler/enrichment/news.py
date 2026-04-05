"""
News-Enrichment via NewsAPI.

httpx für async HTTP, tenacity für Retry-Logik,
TTL-Cache damit derselbe Ticker in einem Run nicht doppelt angefragt wird.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from wsb_crawler.config import get_settings
from wsb_crawler.models import NewsArticle
from wsb_crawler.storage.cache import news_cache

if TYPE_CHECKING:
    from wsb_crawler.storage.database import Database

_db: "Database | None" = None


def set_database(db: "Database") -> None:
    global _db
    _db = db

NEWSAPI_BASE = "https://newsapi.org/v2/everything"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=False,
)
async def get_news(ticker: str, company_name: str | None = None) -> list[NewsArticle]:
    """
    Holt aktuelle News für einen Ticker.

    Sucht nach Ticker-Symbol UND Firmenname (wenn vorhanden) um
    mehr relevante Artikel zu finden.

    Gibt max. 5 Artikel zurück (genug für Discord-Embed).
    """
    cache_key = ticker
    cached = news_cache.get(cache_key)
    if cached is not None:
        logger.debug(f"Cache-Hit für News: {ticker}")
        return cached

    cfg = (await get_settings(_db)).newsapi
    since = (datetime.now(tz=timezone.utc) - timedelta(hours=cfg.window_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    # Suchquery: "$GME OR GameStop" für bessere Trefferquote
    query_parts = [f"${ticker}"]
    if company_name:
        # Nur der erste Teil des Firmennamens (ohne "Inc.", "Corp." etc.)
        short_name = company_name.split()[0]
        if len(short_name) > 3:  # "A" oder "AI" als Suchterm wäre zu breit
            query_parts.append(short_name)
    query = " OR ".join(query_parts)

    params = {
        "q": query,
        "language": cfg.lang,
        "sortBy": "publishedAt",
        "pageSize": 5,
        "from": since,
        "apiKey": cfg.key,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(NEWSAPI_BASE, params=params)
            response.raise_for_status()
            data = response.json()

        articles = [
            NewsArticle(
                ticker=ticker,
                title=a["title"],
                source=a["source"]["name"],
                url=a["url"],
                published_at=datetime.fromisoformat(
                    a["publishedAt"].replace("Z", "+00:00")
                ),
            )
            for a in data.get("articles", [])
            if a.get("title") and a.get("url")
        ]

        news_cache.set(cache_key, articles)
        logger.debug(f"News geholt: {ticker} → {len(articles)} Artikel")
        return articles

    except Exception as e:
        logger.warning(f"Konnte News für {ticker} nicht holen: {e}")
        news_cache.set(cache_key, [])  # Leere Liste cachen um erneute Fehler zu vermeiden
        return []


async def get_news_bulk(
    tickers: list[str],
    company_names: dict[str, str | None] | None = None,
) -> dict[str, list[NewsArticle]]:
    """
    Holt News für mehrere Ticker parallel.
    Gibt {ticker: [NewsArticle, ...]} zurück.
    """
    import asyncio
    names = company_names or {}
    results = await asyncio.gather(
        *[get_news(t, names.get(t)) for t in tickers]
    )
    return dict(zip(tickers, results))
