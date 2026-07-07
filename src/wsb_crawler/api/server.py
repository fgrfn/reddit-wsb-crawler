"""
FastAPI-Server für das WSB-Crawler Dashboard.

Läuft als asyncio-Task parallel zum Crawler-Scheduler.
Serviert das statische HTML-Dashboard (api/static/) unter / und die API unter /api/.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from loguru import logger
from starlette.middleware.base import RequestResponseEndpoint

from wsb_crawler.__version__ import __version__
from wsb_crawler.api.auth import REALM, get_auth_token, request_is_authorized
from wsb_crawler.api.routers import config, dashboard, status
from wsb_crawler.config import is_configured
from wsb_crawler.storage.database import Database

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="WSB-Crawler Dashboard", version=__version__, docs_url="/api/docs")


@app.middleware("http")
async def auth_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Erzwingt HTTP-Basic-Auth, sobald WSB_AUTH_TOKEN gesetzt ist (sonst No-Op)."""
    authorized = request_is_authorized(
        client_host=request.client.host if request.client else None,
        auth_header=request.headers.get("Authorization"),
        method=request.method,
        token=get_auth_token(),
    )
    if not authorized:
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{REALM}"'},
        )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:80",
        "http://localhost:8080",
    ],  # Dev + Prod
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(status.router, prefix="/api")


# Statisches HTML-Dashboard servieren (Single-File, kein Assets-Ordner nötig)
if (STATIC_DIR / "index.html").exists():

    @app.get("/", include_in_schema=False, response_model=None)
    async def serve_root() -> Response:
        """Startseite: beim Erststart direkt zum Setup weiterleiten."""
        db = cast(Database | None, getattr(app.state, "db", None))
        if db is not None and not await is_configured(db):
            return RedirectResponse(url="/setup", status_code=307)
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def serve_spa(full_path: str) -> Response:
        """Alle sonstigen nicht-API-Routen → index.html (SPA-Routing via Hash)."""
        return FileResponse(STATIC_DIR / "index.html")


def set_database(db: Database) -> None:
    """Gibt die DB-Instanz an alle Router weiter (wird in main.py aufgerufen)."""
    config.db = db
    dashboard.db = db
    status.db = db
    app.state.db = db


async def run_server(db: Database, host: str = "127.0.0.1", port: int = 80) -> None:
    """Startet den uvicorn Server als asyncio-Task.

    Default-Bind ist localhost, weil das Dashboard ohne WSB_AUTH_TOKEN keine
    Authentifizierung hat. Für LAN-Zugriff (Docker/NAS) WSB_HOST=0.0.0.0 setzen
    und dringend WSB_AUTH_TOKEN vergeben.
    """
    set_database(db)
    if host not in ("127.0.0.1", "::1", "localhost") and not get_auth_token():
        logger.warning(
            f"Dashboard lauscht auf {host} OHNE WSB_AUTH_TOKEN — die API "
            "(inkl. Secret-Verwaltung) ist ungeschützt im Netzwerk erreichbar. "
            "Setze WSB_AUTH_TOKEN oder binde auf 127.0.0.1."
        )
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
        raise RuntimeError(f"uvicorn konnte nicht starten — Port {port} bereits belegt?") from exc
