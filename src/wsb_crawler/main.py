"""
WSB-Crawler v2 — Haupt-Entry-Point.

Startet den API-Server (Dashboard) und den Scheduler-Loop parallel.
Beim ersten Start ohne Konfiguration → Browser öffnet Setup-Wizard.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
import webbrowser
from datetime import datetime, timezone

from loguru import logger

from wsb_crawler.__version__ import __version__
from wsb_crawler.alerts import bot as discord_bot
from wsb_crawler.alerts.discord import send_alerts, send_heartbeat
from wsb_crawler.analysis.detector import analyze_mentions
from wsb_crawler.api.server import run_server
from wsb_crawler.config import DB_PATH, get_settings
from wsb_crawler.crawler.reddit import crawl_all_subreddits
from wsb_crawler.storage.database import Database

DASHBOARD_URL = "http://localhost:8080"


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


async def run_single_crawl(db: Database) -> None:
    cfg = await get_settings(db)
    run_id = str(uuid.uuid4())

    logger.info(f"═══ Crawl gestartet [{run_id[:8]}] ═══")
    db_run_id = await db.start_run(cfg.crawler.subreddits)

    try:
        result = await crawl_all_subreddits(run_id=db_run_id)
        await db.save_run_mentions(db_run_id, result.mention_counts)
        alerts = await analyze_mentions(result.mention_counts, db)

        sent_count = 0
        if alerts:
            sent_count = await send_alerts(alerts)
            for alert in alerts:
                if alert.sent:
                    await db.set_cooldown(alert.ticker, cfg.alerts.cooldown_h)
                    await db.save_alert(alert)

        await db.finish_run(
            db_run_id,
            posts_scanned=result.posts_scanned,
            comments_scanned=result.comments_scanned,
        )

        duration = result.duration_seconds or 0
        logger.info(
            f"═══ Crawl abgeschlossen [{run_id[:8]}] | "
            f"{result.posts_scanned} Posts | "
            f"{len(result.mention_counts)} Ticker | "
            f"{sent_count} Alerts | "
            f"{duration:.1f}s ═══"
        )

    except Exception as e:
        logger.exception(f"Fehler im Crawl-Lauf: {e}")
        await db.finish_run(db_run_id, 0, 0, is_healthy=False)
        raise


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
            import datetime as dt
            from datetime import timezone
            status.next_run_at = datetime.now(tz=timezone.utc) + dt.timedelta(seconds=interval)
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


async def main_async() -> None:
    _setup_logging()
    logger.info(f"WSB-Crawler v{__version__} startet")

    async with Database(DB_PATH) as db:
        configured = await db.is_configured()

        # Browser öffnen
        url = DASHBOARD_URL if configured else f"{DASHBOARD_URL}/setup"
        logger.info(f"Dashboard: {url}")
        webbrowser.open(url)

        tasks: list[asyncio.Task] = [
            asyncio.create_task(run_server(db)),
            asyncio.create_task(scheduler_loop(db)),
        ]

        # Discord Bot (optional, nur wenn konfiguriert)
        try:
            cfg = await get_settings(db)
            if cfg.discord.bot_token:
                discord_bot.set_database(db)
                tasks.append(asyncio.create_task(discord_bot.start_bot(cfg.discord.bot_token)))
        except RuntimeError:
            pass  # Noch nicht konfiguriert — wird nach Setup gestartet

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
