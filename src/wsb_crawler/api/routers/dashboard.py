"""
Dashboard-Router: Daten für Charts, Ticker-Übersicht und Alert-History.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from wsb_crawler.crawler.runner import run_single_crawl
from wsb_crawler.storage.database import Database

router = APIRouter(tags=["dashboard"])
db: Database = None  # type: ignore[assignment]  # wird in server.py::set_database gesetzt

_crawl_task: asyncio.Task[None] | None = None


def is_crawl_running() -> bool:
    return _crawl_task is not None and not _crawl_task.done()


def _log_crawl_outcome(task: asyncio.Task[None]) -> None:
    """Ohne done-callback verschwinden Exceptions aus fire-and-forget Tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(f"Manuell gestarteter Crawl fehlgeschlagen: {exc}")


@router.get("/tickers")
async def get_top_tickers(days: int = Query(default=7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Top-Ticker der letzten N Tage."""
    entries = await db.get_top_tickers(days=days, limit=20)
    return [
        {
            "ticker": e.ticker,
            "total_mentions": e.total_mentions,
            "avg_daily": round(e.avg_daily_mentions, 1),
            "peak_mentions": e.peak_mentions,
            "peak_day": e.peak_day.isoformat() if e.peak_day else None,
            "trend": e.trend_direction.value,
        }
        for e in entries
    ]


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


@router.get("/runs")
async def get_runs(limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, Any]]:
    """Letzte Crawl-Runs mit Statistiken."""
    rows = await db.get_recent_runs(limit=limit)
    return rows


@router.post("/crawl")
async def trigger_crawl() -> dict[str, Any]:
    """Startet einen Crawl-Lauf manuell (fire-and-forget als asyncio-Task)."""
    global _crawl_task
    if not await db.is_configured():
        raise HTTPException(
            status_code=400,
            detail="Konfiguration unvollständig. Bitte zuerst die Ersteinrichtung abschließen.",
        )
    if is_crawl_running():
        raise HTTPException(status_code=409, detail="Crawl läuft bereits")
    _crawl_task = asyncio.create_task(run_single_crawl(db))
    _crawl_task.add_done_callback(_log_crawl_outcome)
    return {"ok": True}
