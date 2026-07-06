"""
Einzelner Crawl-Lauf — kann sowohl vom Scheduler als auch von der API ausgelöst werden.

Ausgelagert aus main.py damit api/routers/dashboard.py es ohne Zirkular-Import nutzen kann.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from wsb_crawler.alerts.discord import send_alerts
from wsb_crawler.analysis.detector import analyze_mentions
from wsb_crawler.config import get_settings
from wsb_crawler.crawler.reddit import crawl_all_subreddits
from wsb_crawler.storage.database import Database

# Verhindert dass Scheduler und manueller API-Trigger gleichzeitig crawlen
_crawl_lock = asyncio.Lock()

MENTION_RETENTION_DAYS = 90


async def run_single_crawl(db: Database) -> None:
    if _crawl_lock.locked():
        logger.warning("Crawl übersprungen — es läuft bereits ein anderer Crawl")
        return

    async with _crawl_lock:
        await _run_crawl(db)


async def _run_crawl(db: Database) -> None:
    cfg = await get_settings(db)
    run_id = await db.start_run(cfg.crawler.subreddits)

    logger.info(f"═══ Crawl gestartet [{run_id[:8]}] ═══")

    try:
        result = await crawl_all_subreddits(run_id=run_id)
        await db.save_run_mentions(run_id, result.mention_counts)
        # run_id ausschließen: die gerade gespeicherten Mentions dürfen die
        # History-Queries nicht beeinflussen (sonst nie NEW_TICKER-Alerts)
        alerts = await analyze_mentions(result.mention_counts, db, run_id=run_id)

        sent_count = 0
        if alerts:
            sent_count = await send_alerts(alerts)
            for alert in alerts:
                if alert.sent:
                    await db.set_cooldown(alert.ticker, cfg.alerts.cooldown_h)
                    await db.save_alert(alert)

        await db.finish_run(
            run_id,
            posts_scanned=result.posts_scanned,
            comments_scanned=result.comments_scanned,
        )

        purged = await db.purge_old_mentions(days=MENTION_RETENTION_DAYS)
        if purged:
            logger.debug(f"{purged} Mentions älter als {MENTION_RETENTION_DAYS} Tage gelöscht")

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
        await db.finish_run(run_id, 0, 0, is_healthy=False)
        raise
