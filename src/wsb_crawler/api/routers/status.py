"""
Status-Router: aktueller Crawler-Zustand und Live-Log via WebSocket.
"""

from __future__ import annotations

import asyncio
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from wsb_crawler.api.routers.dashboard import is_crawl_running
from wsb_crawler.storage.database import Database

router = APIRouter(tags=["status"])
db: Database  # wird in server.py gesetzt

# Ring-Buffer für letzte 200 Log-Zeilen (für WebSocket-Clients die sich verbinden)
_log_buffer: deque[str] = deque(maxlen=200)
_ws_clients: list[WebSocket] = []


def _setup_ws_log_sink() -> None:
    """Loguru-Sink der Log-Messages in den WebSocket-Buffer schreibt."""

    async def _broadcast(message: str) -> None:
        disconnected = []
        for ws in _ws_clients:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            _ws_clients.remove(ws)

    def _sink(message: "logger.Message") -> None:  # type: ignore[name-defined]
        line = str(message).rstrip("\n")
        if not line:
            return

        # Immer im Ring-Buffer halten, damit neue Clients sofort Verlauf sehen.
        _log_buffer.append(line)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_broadcast(line))
        except RuntimeError:
            pass

    logger.add(_sink, format="{time:HH:mm:ss} | {level: <8} | {message}", level="INFO")


_setup_ws_log_sink()


@router.get("/status")
async def get_status() -> dict:
    """Aktueller Crawler-Status."""
    run_status = await db.get_run_status()
    configured = await db.is_configured()
    return {
        "configured": configured,
        "last_run_at": run_status.last_run_at.isoformat() if run_status.last_run_at else None,
        "last_run_duration_s": run_status.last_run_duration_seconds,
        "total_runs": run_status.total_runs,
        "total_alerts": run_status.total_alerts_sent,
        "tracked_tickers": run_status.tracked_tickers,
        "next_run_at": run_status.next_run_at.isoformat() if run_status.next_run_at else None,
        "is_healthy": run_status.is_healthy,
        "crawl_running": is_crawl_running(),
    }


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    """WebSocket-Endpoint für Live-Log-Stream."""
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        # Zuerst Buffer senden (damit neue Clients Geschichte sehen)
        for line in list(_log_buffer):
            await websocket.send_text(line)
        # Verbindung offen halten
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
