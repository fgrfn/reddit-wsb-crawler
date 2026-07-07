"""
Tests für Dashboard- und Status-Router (direkte Endpoint-Aufrufe).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wsb_crawler.api.routers import dashboard as dashboard_router
from wsb_crawler.api.routers import status as status_router
from wsb_crawler.models import MarketStatus, PriceData
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
        # Angereicherte Felder sind vorhanden (Cache leer → price/name None)
        gme = next(r for r in result if r["ticker"] == "GME")
        assert gme["trend"] in ("up", "down", "flat")
        assert "company_name" in gme and "price" in gme and "price_change" in gme

    async def test_ticker_detail_enriched(self, db: Database):
        run_id = await db.start_run(["wsb"])
        await db.save_run_mentions(run_id, {"GME": 20})
        dummy = PriceData(
            ticker="GME",
            company_name="GameStop",
            price=42.0,
            change_24h=3.0,
            market_status=MarketStatus.OPEN,
        )
        with (
            patch(
                "wsb_crawler.api.routers.dashboard.get_price",
                new=AsyncMock(return_value=dummy),
            ),
            patch(
                "wsb_crawler.api.routers.dashboard.resolve_name",
                new=AsyncMock(return_value="GameStop Corp."),
            ),
        ):
            detail = await dashboard_router.get_ticker_detail("gme", days=30)
        assert detail["ticker"] == "GME"
        assert detail["company_name"] == "GameStop Corp."
        assert detail["price"] == 42.0
        assert detail["price_change"] == 3.0

    async def test_ticker_history(self, db: Database):
        run_id = await db.start_run(["wsb"])
        await db.save_run_mentions(run_id, {"GME": 20})
        result = await dashboard_router.get_ticker_history("gme", days=30)
        assert result["ticker"] == "GME"
        assert len(result["data"]) == 1

    async def test_daily_mentions_endpoint(self, db: Database):
        run_id = await db.start_run(["wsb"])
        await db.save_run_mentions(run_id, {"GME": 20, "AMC": 5})
        result = await dashboard_router.get_daily_mentions(days=14)
        assert result["days"] == 14
        assert len(result["data"]) == 1
        assert result["data"][0]["mentions"] == 25  # 20 + 5 über alle Ticker

    async def test_runs_endpoint(self, db: Database):
        run_id = await db.start_run(["wsb"])
        await db.finish_run(run_id, 100, 50)
        runs = await dashboard_router.get_runs(limit=10)
        assert len(runs) == 1
        assert runs[0]["posts_scanned"] == 100

    async def test_run_detail_endpoint(self, db: Database):
        run_id = await db.start_run(["wsb"])
        await db.save_run_mentions(run_id, {"GME": 20, "AMC": 5})
        await db.finish_run(run_id, 100, 50)

        detail = await dashboard_router.get_run_detail(run_id)

        assert detail["id"] == run_id
        assert detail["posts_scanned"] == 100
        assert [m["ticker"] for m in detail["mentions"]] == ["GME", "AMC"]

    async def test_cron_preview_endpoint(self):
        now = datetime(2026, 7, 7, 12, 15, tzinfo=UTC)
        with patch("wsb_crawler.api.routers.dashboard.datetime") as dt_mock:
            dt_mock.now.return_value = now
            result = await dashboard_router.preview_cron("0 */2 * * *", count=3)

        assert result["next_runs"] == [
            datetime(2026, 7, 7, 14, 0, tzinfo=UTC).isoformat(),
            datetime(2026, 7, 7, 16, 0, tzinfo=UTC).isoformat(),
            datetime(2026, 7, 7, 18, 0, tzinfo=UTC).isoformat(),
        ]


class TestStatusEndpoint:
    async def test_status_reports_unconfigured(self, db: Database):
        result = await status_router.get_status()
        assert result["configured"] is False
        assert result["total_runs"] == 0
        assert result["next_run_at"] is None

    async def test_status_after_configuration(self, db: Database):
        await db.set_setting("reddit_client_id", "x")
        await db.set_setting("reddit_client_secret", "y")
        await db.set_setting("discord_webhook_url", "https://discord.com/api/webhooks/1/z")
        result = await status_router.get_status()
        assert result["configured"] is True

    async def test_status_calculates_next_interval_run(self, db: Database):
        await db.set_setting("reddit_client_id", "x")
        await db.set_setting("reddit_client_secret", "y")
        await db.set_setting("discord_webhook_url", "https://discord.com/api/webhooks/1/z")
        await db.set_setting("crawl_interval_minutes", "30")

        now = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)
        with patch("wsb_crawler.api.routers.status.datetime") as dt_mock:
            dt_mock.now.return_value = now
            result = await status_router.get_status()

        assert result["next_run_at"] == (now + timedelta(minutes=30)).isoformat()

    async def test_status_calculates_next_cron_run(self, db: Database):
        await db.set_setting("reddit_client_id", "x")
        await db.set_setting("reddit_client_secret", "y")
        await db.set_setting("discord_webhook_url", "https://discord.com/api/webhooks/1/z")
        await db.set_setting("schedule_mode", "cron")
        await db.set_setting("cron_expression", "0 */2 * * *")

        with patch("wsb_crawler.api.routers.status.datetime") as dt_mock:
            dt_mock.now.return_value = datetime(2026, 7, 7, 12, 15, tzinfo=UTC)
            result = await status_router.get_status()

        assert result["next_run_at"] == datetime(2026, 7, 7, 14, 0, tzinfo=UTC).isoformat()
