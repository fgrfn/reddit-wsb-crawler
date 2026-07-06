"""
Tests für Dashboard- und Status-Router (direkte Endpoint-Aufrufe).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wsb_crawler.api.routers import dashboard as dashboard_router
from wsb_crawler.api.routers import status as status_router
from wsb_crawler.storage.database import Database


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.init()
    dashboard_router.db = database
    status_router.db = database
    yield database
    await database.close()


class TestDashboardEndpoints:
    async def test_tickers_empty(self, db: Database):
        assert await dashboard_router.get_top_tickers(days=7) == []

    async def test_tickers_after_run(self, db: Database):
        run_id = await db.start_run(["wsb"])
        await db.save_run_mentions(run_id, {"GME": 20, "AMC": 5})
        result = await dashboard_router.get_top_tickers(days=7)
        tickers = {r["ticker"] for r in result}
        assert "GME" in tickers

    async def test_ticker_history(self, db: Database):
        run_id = await db.start_run(["wsb"])
        await db.save_run_mentions(run_id, {"GME": 20})
        result = await dashboard_router.get_ticker_history("gme", days=30)
        assert result["ticker"] == "GME"
        assert len(result["data"]) == 1

    async def test_runs_endpoint(self, db: Database):
        run_id = await db.start_run(["wsb"])
        await db.finish_run(run_id, 100, 50)
        runs = await dashboard_router.get_runs(limit=10)
        assert len(runs) == 1
        assert runs[0]["posts_scanned"] == 100


class TestStatusEndpoint:
    async def test_status_reports_unconfigured(self, db: Database):
        result = await status_router.get_status()
        assert result["configured"] is False
        assert result["total_runs"] == 0

    async def test_status_after_configuration(self, db: Database):
        await db.set_setting("reddit_client_id", "x")
        await db.set_setting("reddit_client_secret", "y")
        await db.set_setting("discord_webhook_url", "https://discord.com/api/webhooks/1/z")
        result = await status_router.get_status()
        assert result["configured"] is True
