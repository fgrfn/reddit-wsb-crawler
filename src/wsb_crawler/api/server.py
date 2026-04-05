"""
FastAPI-Server für das WSB-Crawler Dashboard.

Läuft als asyncio-Task parallel zum Crawler-Scheduler.
Serviert die React-App (web/dist/) unter / und die API unter /api/.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from wsb_crawler.api.routers import config, dashboard, status
from wsb_crawler.storage.database import Database

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="WSB-Crawler Dashboard", version="2.0.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router,    prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(status.router,    prefix="/api")

# Statisches React-Build servieren (nur wenn vorhanden)
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """Alle nicht-API-Routen → React index.html (SPA-Routing)."""
        return FileResponse(STATIC_DIR / "index.html")


def set_database(db: Database) -> None:
    """Gibt die DB-Instanz an alle Router weiter (wird in main.py aufgerufen)."""
    config.db = db
    dashboard.db = db
    status.db = db


async def run_server(db: Database, host: str = "0.0.0.0", port: int = 8080) -> None:
    """Startet den uvicorn Server als asyncio-Task."""
    set_database(db)
    config_uvicorn = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",  # uvicorn-eigene Logs unterdrücken (loguru übernimmt)
        access_log=False,
    )
    server = uvicorn.Server(config_uvicorn)
    logger.info(f"Dashboard läuft auf http://{host}:{port}")
    try:
        await server.serve()
    except SystemExit as exc:
        raise RuntimeError(
            f"uvicorn konnte nicht starten — Port {port} bereits belegt?"
        ) from exc
