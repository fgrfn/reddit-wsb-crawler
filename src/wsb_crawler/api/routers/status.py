"""
Status-Router: aktueller Crawler-Zustand und Live-Streams via WebSocket.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from wsb_crawler.api.routers.dashboard import is_crawl_running
from wsb_crawler.config import is_configured
from wsb_crawler.runtime.progress import snapshot as progress_snapshot
from wsb_crawler.storage.database import Database

router = APIRouter(tags=["status"])
db: Database = None  # type: ignore[assignment]  # wird in server.py::set_database gesetzt

# Ring-Buffer für letzte 200 Log-Zeilen (für WebSocket-Clients die sich verbinden)
_log_buffer: deque[str] = deque(maxlen=200)
_ws_clients: list[WebSocket] = []
# Starke Referenzen auf Broadcast-Tasks — sonst kann der GC laufende Tasks einsammeln
_broadcast_tasks: set[asyncio.Task[None]] = set()


def setup_ws_log_sink() -> None:
    """Loguru-Sink der Log-Messages in den WebSocket-Buffer schreibt.

    Muss explizit NACH logger.remove() / _setup_logging() aufgerufen werden,
    da logger.remove() alle Sinks entfernt — auch diesen.
    """

    async def _broadcast(message: str) -> None:
        disconnected = []
        for ws in _ws_clients:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            _ws_clients.remove(ws)

    def _sink(message: object) -> None:
        line = str(message).rstrip("\n")
        if not line:
            return

        # Immer im Ring-Buffer halten, damit neue Clients sofort Verlauf sehen.
        _log_buffer.append(line)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Log-Aufruf außerhalb des Event-Loops (z.B. aus to_thread) —
            # Zeile bleibt im Buffer, Broadcast holt der nächste Reconnect nach
            return
        task = loop.create_task(_broadcast(line))
        _broadcast_tasks.add(task)
        task.add_done_callback(_broadcast_tasks.discard)

    logger.add(_sink, format="{time:HH:mm:ss} | {level: <8} | {message}", level="INFO")


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Aktueller Crawler-Status."""
    return await _status_payload()


async def _status_payload() -> dict[str, Any]:
    """Build the status payload shared by HTTP and WebSocket clients."""
    run_status = await db.get_run_status()
    configured = await is_configured(db)
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
        "current_run": progress_snapshot(),
    }


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    """WebSocket-Endpoint für Live-Log-Stream."""
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        # Clear-Signal + Buffer senden. Das Clear stellt sicher, dass beim
        # Reconnect die Logs nicht doppelt angezeigt werden.
        await websocket.send_text("__LOGS_CLEAR__")
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


@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket) -> None:
    """WebSocket-Endpoint fuer den Live-Dashboard-Status."""
    await websocket.accept()
    last_payload: dict[str, Any] | None = None
    last_sent_at = 0.0
    try:
        while True:
            payload = await _status_payload()
            now = asyncio.get_running_loop().time()
            if payload != last_payload or now - last_sent_at >= 30:
                await websocket.send_json(payload)
                last_payload = payload
                last_sent_at = now
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Browser disconnects can surface as send errors depending on timing.
        logger.debug("Dashboard-Status-WebSocket getrennt")
