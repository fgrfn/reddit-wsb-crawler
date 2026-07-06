"""
WSB-Crawler v2 — Haupt-Entry-Point.

Startet den API-Server (Dashboard) und den Scheduler-Loop parallel.
Beim ersten Start ohne Konfiguration → Browser öffnet Setup-Wizard.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import os
import signal
import sys
import webbrowser
from datetime import datetime

from loguru import logger

from wsb_crawler.__version__ import __version__
from wsb_crawler.alerts import bot as discord_bot
from wsb_crawler.alerts.discord import send_heartbeat
from wsb_crawler.alerts.discord import set_database as discord_set_db
from wsb_crawler.api.routers.status import setup_ws_log_sink
from wsb_crawler.api.server import run_server
from wsb_crawler.config import DB_PATH, get_settings
from wsb_crawler.crawler.reddit import set_database as reddit_set_db
from wsb_crawler.crawler.runner import run_single_crawl
from wsb_crawler.enrichment.news import set_database as news_set_db
from wsb_crawler.storage.database import Database

PORT = int(os.getenv("WSB_PORT", "80"))
# Default: nur localhost — das Dashboard hat keine Authentifizierung.
# Für LAN-Zugriff (z.B. Docker/NAS) explizit WSB_HOST=0.0.0.0 setzen.
HOST = os.getenv("WSB_HOST", "127.0.0.1")
DASHBOARD_URL = f"http://localhost:{PORT}"

BOT_RETRY_SECONDS = 60


def _setup_logging(log_level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level=log_level,
        colorize=True,
    )
    logger.add(
        "logs/crawler.log",
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} | {message}",
    )


async def scheduler_loop(db: Database) -> None:
    """Wartet auf vollständige Konfiguration, dann regelmäßige Crawls."""
    # Warten bis Setup abgeschlossen
    while not await db.is_configured():
        logger.info("Warte auf Konfiguration via Dashboard...")
        await asyncio.sleep(5)

    cfg = await get_settings(db)
    interval = cfg.crawler.crawl_interval_minutes * 60

    logger.info(f"Scheduler gestartet — Intervall: {cfg.crawler.crawl_interval_minutes} Minuten")

    while True:
        try:
            await run_single_crawl(db)
        except Exception as e:
            logger.error(f"Crawl fehlgeschlagen: {e}")

        try:
            status = await db.get_run_status()
            status.next_run_at = datetime.now(tz=dt.UTC) + dt.timedelta(seconds=interval)
            await send_heartbeat(status)
        except Exception as e:
            logger.warning(f"Heartbeat fehlgeschlagen: {e}")

        # Intervall neu laden (könnte per Dashboard geändert worden sein)
        try:
            cfg = await get_settings(db)
            interval = cfg.crawler.crawl_interval_minutes * 60
        except Exception:
            pass

        logger.info(f"Nächster Lauf in {interval // 60} Minuten...")
        await asyncio.sleep(interval)


async def bot_supervisor(db: Database) -> None:
    """Startet den Discord-Bot sobald ein Token konfiguriert ist.

    Läuft dauerhaft: greift auch, wenn der Token erst nach dem Start über
    den Setup-Wizard oder die Config-Seite eingetragen wird, und startet
    den Bot nach Verbindungsabbrüchen neu.
    """
    discord_bot.set_database(db)
    while True:
        token = (await db.get_setting("discord_bot_token") or "").strip()
        token = os.getenv("DISCORD_BOT_TOKEN", "").strip() or token
        if token:
            logger.info("Discord-Bot wird gestartet...")
            await discord_bot.start_bot(token)
            logger.warning(f"Discord-Bot beendet — neuer Versuch in {BOT_RETRY_SECONDS}s")
        await asyncio.sleep(BOT_RETRY_SECONDS)


def _install_sigterm_handler(tasks: list[asyncio.Task[None]]) -> None:
    """Sorgt dafür, dass docker stop / systemd stop sauber herunterfahren."""

    def _cancel_all() -> None:
        logger.info("SIGTERM empfangen — fahre herunter...")
        for task in tasks:
            task.cancel()

    # Windows: add_signal_handler wirft NotImplementedError — dort reicht KeyboardInterrupt
    with contextlib.suppress(NotImplementedError):
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, _cancel_all)


async def main_async() -> None:
    async with Database(DB_PATH) as db:
        # Log-Level: ENV hat Vorrang, dann DB-Setting, dann INFO
        log_level = (
            os.getenv("LOG_LEVEL", "").strip() or (await db.get_setting("log_level") or "INFO")
        ).upper()
        _setup_logging(log_level)
        # WebSocket-Log-Sink NACH logger.remove() registrieren — sonst wird er
        # durch _setup_logging() entfernt und die Log-Seite im Dashboard bleibt leer.
        setup_ws_log_sink()
        logger.info(f"WSB-Crawler v{__version__} startet")

        configured = await db.is_configured()

        # DB in alle Module injecten, die get_settings() benötigen
        reddit_set_db(db)
        discord_set_db(db)
        news_set_db(db)

        # Browser öffnen (nicht in Docker/Headless — WSB_NO_BROWSER=1)
        url = DASHBOARD_URL if configured else f"{DASHBOARD_URL}/setup"
        logger.info(f"Dashboard: {url}")
        if os.getenv("WSB_NO_BROWSER", "") != "1":
            webbrowser.open(url)

        tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(run_server(db, host=HOST, port=PORT)),
            asyncio.create_task(scheduler_loop(db)),
            asyncio.create_task(bot_supervisor(db)),
        ]
        _install_sigterm_handler(tasks)

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Crawler wird beendet...")
        finally:
            for task in tasks:
                task.cancel()


def main() -> None:
    """Synchroner Entry-Point für pyproject.toml scripts."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Manuell beendet.")


if __name__ == "__main__":
    main()
