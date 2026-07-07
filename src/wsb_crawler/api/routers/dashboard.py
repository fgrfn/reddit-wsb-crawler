"""
Dashboard-Router: Daten für Charts, Ticker-Übersicht und Alert-History.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from wsb_crawler.__version__ import __version__
from wsb_crawler.analysis.trends import get_top_tickers_cached
from wsb_crawler.config import is_configured
from wsb_crawler.crawler.runner import (
    is_crawl_running as runner_is_crawl_running,
)
from wsb_crawler.crawler.runner import (
    run_single_crawl,
    stop_current_crawl,
)
from wsb_crawler.enrichment.prices import get_price
from wsb_crawler.enrichment.resolver import resolve_name
from wsb_crawler.storage.database import Database

router = APIRouter(tags=["dashboard"])
db: Database = None  # type: ignore[assignment]  # wird in server.py::set_database gesetzt

_crawl_task: asyncio.Task[None] | None = None


def is_crawl_running() -> bool:
    return runner_is_crawl_running() or (_crawl_task is not None and not _crawl_task.done())


def _log_crawl_outcome(task: asyncio.Task[None]) -> None:
    """Ohne done-callback verschwinden Exceptions aus fire-and-forget Tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(f"Manuell gestarteter Crawl fehlgeschlagen: {exc}")


@router.get("/about")
async def get_about() -> dict[str, str | None]:
    """Build-/Versionsinfo für Dashboard und Smoke-Tests."""
    return {
        "version": __version__,
        "build_commit": os.getenv("WSB_BUILD_COMMIT") or os.getenv("GIT_COMMIT"),
        "build_date": os.getenv("WSB_BUILD_DATE"),
    }


@router.get("/tickers")
async def get_top_tickers(
    days: int = Query(default=7, ge=1, le=90),
) -> list[dict[str, Any]]:
    """Top-Ticker der letzten N Tage (Trend berechnet, Name/Kurs cache-only)."""
    entries = await get_top_tickers_cached(db, days=days, limit=20)
    return [
        {
            "ticker": e.ticker,
            "total_mentions": e.total_mentions,
            "avg_daily": round(e.avg_daily_mentions, 1),
            "peak_mentions": e.peak_mentions,
            "peak_day": e.peak_day.isoformat() if e.peak_day else None,
            "trend": e.trend_direction.value,
            "company_name": e.company_name,
            "price": e.current_price,
            "price_change": e.price_change_period,
        }
        for e in entries
    ]


@router.get("/tickers/{ticker}")
async def get_ticker_detail(
    ticker: str,
    days: int = Query(default=30, ge=1, le=90),
) -> dict[str, Any]:
    """Kompakte Detaildaten für eine Ticker-Detailseite."""
    symbol = ticker.upper().lstrip("$")
    history = await db.get_ticker_history(symbol, days=days)
    alerts = await db.get_alert_history(limit=20, ticker=symbol)
    total_mentions = sum(count for _, count in history.mention_counts)
    peak = max((count for _, count in history.mention_counts), default=0)
    latest = history.mention_counts[-1][1] if history.mention_counts else 0

    # Einzelner Ticker → frischer Kurs/Name ist unkritisch (kein Burst).
    # get_price/resolve_name cachen selbst und fangen Fehler ab (→ None).
    price = await get_price(symbol)
    company_name = await resolve_name(symbol)

    return {
        "ticker": symbol,
        "days": days,
        "company_name": company_name,
        "price": price.primary_price if price else None,
        "price_change": price.primary_change if price else None,
        "currency": price.currency if price else None,
        "total_mentions": total_mentions,
        "latest_mentions": latest,
        "peak_mentions": peak,
        "avg_mentions": round(history.avg_mentions, 2),
        "trend": history.trend_direction.value,
        "alerts": alerts,
        "history": [
            {"date": ts.isoformat(), "mentions": count} for ts, count in history.mention_counts
        ],
    }


@router.get("/tickers/{ticker}/history")
async def get_ticker_history(
    ticker: str,
    days: int = Query(default=30, ge=1, le=90),
) -> dict[str, Any]:
    """Mention-History eines einzelnen Tickers (für Chart)."""
    history = await db.get_ticker_history(ticker.upper(), days=days)
    return {
        "ticker": history.ticker,
        "data": [
            {"date": ts.isoformat(), "mentions": count} for ts, count in history.mention_counts
        ],
        "avg": round(history.avg_mentions, 1),
        "trend": history.trend_direction.value,
    }


@router.get("/alerts")
async def get_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    ticker: str | None = None,
) -> list[dict[str, Any]]:
    """Alert-History, optional gefiltert nach Ticker."""
    rows = await db.get_alert_history(limit=limit, ticker=ticker)
    return rows


@router.get("/mentions/daily")
async def get_daily_mentions(
    days: int = Query(default=14, ge=1, le=90),
) -> dict[str, Any]:
    """Tägliche Gesamt-Nennungen über alle Ticker (Übersichts-Chart)."""
    totals = await db.get_daily_mention_totals(days=days)
    return {
        "days": days,
        "data": [{"date": ts.isoformat(), "mentions": count} for ts, count in totals],
    }


@router.get("/runs")
async def get_runs(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Letzte Crawl-Runs mit Statistiken."""
    rows = await db.get_recent_runs(limit=limit)
    return rows


@router.post("/crawl")
async def trigger_crawl(dry_run: bool = Query(default=False)) -> dict[str, Any]:
    """Startet einen Crawl-Lauf manuell (fire-and-forget als asyncio-Task)."""
    global _crawl_task
    if not await is_configured(db):
        raise HTTPException(
            status_code=400,
            detail="Konfiguration unvollständig. Bitte zuerst die Ersteinrichtung abschließen.",
        )
    if is_crawl_running():
        raise HTTPException(status_code=409, detail="Crawl läuft bereits")
    _crawl_task = asyncio.create_task(run_single_crawl(db, dry_run=dry_run))
    _crawl_task.add_done_callback(_log_crawl_outcome)
    return {"ok": True, "dry_run": dry_run}


@router.post("/crawl/stop")
async def stop_crawl() -> dict[str, Any]:
    """Stoppt einen laufenden Crawl-Lauf, egal ob manuell oder vom Scheduler gestartet."""
    if not stop_current_crawl():
        raise HTTPException(status_code=409, detail="Kein laufender Crawl")
    return {"ok": True, "stopping": True}
