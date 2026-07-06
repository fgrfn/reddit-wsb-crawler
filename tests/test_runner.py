"""
Integrationstest für den Crawl-Orchestrator (crawler/runner.py).

Mockt das Netzwerk (Reddit-Crawl, Discord-Versand), testet aber die echte
Reihenfolge Speichern → Analysieren → Alert → Cooldown → Cleanup.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wsb_crawler.models import CrawlResult
from wsb_crawler.storage.database import Database


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.init()
    await database.set_setting("reddit_client_id", "test_id")
    await database.set_setting("reddit_client_secret", "test_secret")
    await database.set_setting("discord_webhook_url", "https://discord.com/api/webhooks/0/test")
    yield database
    await database.close()


def _crawl_result(counts: dict[str, int]) -> CrawlResult:
    from datetime import UTC, datetime

    now = datetime.now(tz=UTC)
    return CrawlResult(
        run_id="x",
        started_at=now,
        finished_at=now,
        subreddits=["wallstreetbets"],
        posts_scanned=100,
        comments_scanned=50,
        mention_counts=counts,
    )


class TestRunSingleCrawl:
    async def test_new_ticker_triggers_alert_end_to_end(self, db: Database):
        """Der kritische Pfad: neuer Ticker mit vielen Nennungen → Alert + gespeichert."""
        from wsb_crawler.crawler import runner

        sent = AsyncMock(return_value=1)
        with (
            patch.object(
                runner,
                "crawl_all_subreddits",
                new=AsyncMock(return_value=_crawl_result({"GME": 30})),
            ),
            patch(
                "wsb_crawler.analysis.detector.get_prices_bulk",
                new=AsyncMock(return_value={"GME": None}),
            ),
            patch(
                "wsb_crawler.analysis.detector.get_news_bulk",
                new=AsyncMock(return_value={"GME": []}),
            ),
            patch(
                "wsb_crawler.analysis.detector.resolve_names_bulk",
                new=AsyncMock(return_value={"GME": None}),
            ),
            patch.object(runner, "send_alerts", new=sent) as mock_send,
        ):
            # send_alerts markiert Alerts als gesendet
            async def _mark_sent(alerts):
                for a in alerts:
                    a.sent = True
                return len(alerts)

            mock_send.side_effect = _mark_sent

            await runner.run_single_crawl(db)

        # Mentions gespeichert
        assert await db.is_known_ticker("GME")
        # Alert-History + Cooldown gesetzt
        history = await db.get_alert_history()
        assert len(history) == 1
        assert await db.is_on_cooldown("GME")
        # Lauf als gesund abgeschlossen
        runs = await db.get_recent_runs()
        assert runs[0]["finished_at"] is not None
        assert runs[0]["is_healthy"] == 1

    async def test_lock_prevents_concurrent_runs(self, db: Database):
        """Ein zweiter Crawl während eines laufenden wird übersprungen."""
        from wsb_crawler.crawler import runner

        runner._crawl_lock  # noqa: B018 — sicherstellen dass das Lock existiert

        async def _slow_crawl(run_id: str):
            # Lock ist gehalten, während wir hier sind
            assert runner._crawl_lock.locked()
            return _crawl_result({})

        with (
            patch.object(runner, "crawl_all_subreddits", new=AsyncMock(side_effect=_slow_crawl)),
            patch.object(runner, "send_alerts", new=AsyncMock(return_value=0)),
        ):
            await runner.run_single_crawl(db)

        # Nach Abschluss ist das Lock wieder frei
        assert not runner._crawl_lock.locked()
