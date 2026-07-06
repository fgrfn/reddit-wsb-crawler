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
from wsb_crawler.runtime.progress import add_diagnostic, finish_run, start_run, update_run
from wsb_crawler.storage.database import Database

# Verhindert dass Scheduler und manueller API-Trigger gleichzeitig crawlen
_crawl_lock = asyncio.Lock()

MENTION_RETENTION_DAYS = 90


async def run_single_crawl(db: Database, *, dry_run: bool = False) -> None:
    if _crawl_lock.locked():
        logger.warning("Crawl übersprungen — es läuft bereits ein anderer Crawl")
        return

    async with _crawl_lock:
        await _run_crawl(db, dry_run=dry_run)


async def _run_crawl(db: Database, *, dry_run: bool = False) -> None:
    cfg = await get_settings(db)
    run_id = await db.start_run(cfg.crawler.subreddits)
    start_run(run_id, cfg.crawler.subreddits, dry_run=dry_run)

    mode = "Dry-Run" if dry_run else "Live"
    logger.info(f"═══ Crawl gestartet [{run_id[:8]}] | {mode} ═══")
    logger.info(
        "Crawl-Plan: {} Subreddits | {} Posts/Subreddit | {} Kommentare/Post",
        len(cfg.crawler.subreddits),
        cfg.crawler.posts_limit,
        cfg.crawler.comments_limit,
    )
    if dry_run:
        add_diagnostic("info", "Dry-Run aktiv: Discord-Alerts und Cooldowns werden nicht geschrieben.", source="crawl")

    try:
        update_run(
            phase="reddit",
            phase_label="Reddit lesen",
            message="Posts und Top-Kommentare werden von Reddit geladen…",
            progress=8,
        )
        result = await crawl_all_subreddits(run_id=run_id)

        update_run(
            phase="save",
            phase_label="Daten speichern",
            message=f"Speichere Mentions für {len(result.mention_counts)} erkannte Ticker…",
            progress=50,
            posts_scanned=result.posts_scanned,
            comments_scanned=result.comments_scanned,
            tickers_found=len(result.mention_counts),
            top_tickers=result.top_tickers[:10],
        )
        await db.save_run_mentions(run_id, result.mention_counts)

        # run_id ausschließen: die gerade gespeicherten Mentions dürfen die
        # History-Queries nicht beeinflussen (sonst nie NEW_TICKER-Alerts)
        update_run(
            phase="analysis",
            phase_label="Spikes analysieren",
            message="Vergleiche aktuelle Nennungen mit der historischen 30-Tage-Basis…",
            progress=60,
        )
        alerts = await analyze_mentions(result.mention_counts, db, run_id=run_id)

        sent_count = 0
        if alerts:
            update_run(
                phase="alerts",
                phase_label="Alerts senden",
                message=(
                    f"Dry-Run: {len(alerts)} Alert(s) würden gesendet."
                    if dry_run
                    else f"Sende {len(alerts)} Alert(s) an Discord…"
                ),
                progress=86,
            )
            if dry_run:
                logger.info(f"Dry-Run: {len(alerts)} Alert(s) nicht an Discord gesendet")
                update_run(alerts_sent=0, progress=92)
            else:
                sent_count = await send_alerts(alerts)
                update_run(
                    alerts_sent=sent_count,
                    message=f"{sent_count} Alert(s) gesendet…",
                    progress=92,
                )
                for alert in alerts:
                    if alert.sent:
                        await db.set_cooldown(alert.ticker, cfg.alerts.cooldown_h)
                        await db.save_alert(alert)
        else:
            update_run(
                phase="alerts",
                phase_label="Alerts senden",
                message="Keine Alerts ausgelöst.",
                progress=88,
                alerts_sent=0,
            )

        update_run(
            phase="cleanup",
            phase_label="Aufräumen",
            message="Lauf abschließen und alte Mentions bereinigen…",
            progress=95,
        )
        await db.finish_run(
            run_id,
            posts_scanned=result.posts_scanned,
            comments_scanned=result.comments_scanned,
        )

        purged = await db.purge_old_mentions(days=MENTION_RETENTION_DAYS)
        if purged:
            logger.debug(f"{purged} Mentions älter als {MENTION_RETENTION_DAYS} Tage gelöscht")

        duration = result.duration_seconds or 0
        message = (
            f"Crawl abgeschlossen: {result.posts_scanned} Posts, "
            f"{result.comments_scanned} Kommentare, {len(result.mention_counts)} Ticker, "
            f"{sent_count} Alerts"
        )
        if dry_run:
            message += f" (Dry-Run, {len(alerts)} Alert-Vorschau)"
        finish_run(success=True, message=message, alerts_sent=sent_count)
        logger.info(
            f"═══ Crawl abgeschlossen [{run_id[:8]}] | "
            f"{result.posts_scanned} Posts | "
            f"{len(result.mention_counts)} Ticker | "
            f"{sent_count} Alerts | "
            f"{duration:.1f}s ═══"
        )

    except Exception as e:
        logger.exception(f"Fehler im Crawl-Lauf: {e}")
        finish_run(success=False, message=f"Crawl fehlgeschlagen: {e}")
        await db.finish_run(run_id, 0, 0, is_healthy=False)
        raise
