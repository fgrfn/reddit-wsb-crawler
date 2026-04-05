"""
Tests für den Spike-Detektor (analysis/detector.py).

Nutzt eine In-Memory SQLite DB — kein Mocking nötig.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wsb_crawler.models import AlertReason, MarketStatus, PriceData
from wsb_crawler.storage.database import Database


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    """In-Memory DB für jeden Test."""
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


@pytest.fixture
def mock_enrichment():
    """Patcht alle externen API-Calls (kein Netzwerk in Tests)."""
    dummy_price = PriceData(
        ticker="GME",
        company_name="GameStop Corp.",
        price=42.0,
        currency="USD",
        change_24h=8.5,
        market_status=MarketStatus.OPEN,
    )
    with (
        patch(
            "wsb_crawler.analysis.detector.get_prices_bulk",
            new=AsyncMock(return_value={"GME": dummy_price}),
        ),
        patch(
            "wsb_crawler.analysis.detector.get_news_bulk",
            new=AsyncMock(return_value={"GME": []}),
        ),
        patch(
            "wsb_crawler.analysis.detector.resolve_names_bulk",
            new=AsyncMock(return_value={"GME": "GameStop Corp."}),
        ),
    ):
        yield


class TestSpikeDetection:
    async def test_new_ticker_triggers_alert(self, db: Database, mock_enrichment):
        """Neuer Ticker mit genug Nennungen löst NEW_TICKER Alert aus."""
        from wsb_crawler.analysis.detector import analyze_mentions

        # GME ist neu (noch keine History in DB) mit 25 Nennungen (> min_abs=20)
        alerts = await analyze_mentions({"GME": 25}, db)

        assert len(alerts) == 1
        assert alerts[0].ticker == "GME"
        assert alerts[0].reason == AlertReason.NEW_TICKER

    async def test_new_ticker_below_threshold_no_alert(self, db: Database, mock_enrichment):
        """Neuer Ticker mit zu wenig Nennungen löst keinen Alert aus."""
        from wsb_crawler.analysis.detector import analyze_mentions

        alerts = await analyze_mentions({"GME": 5}, db)  # < min_abs=20
        assert len(alerts) == 0

    async def test_known_ticker_spike_triggers_alert(self, db: Database, mock_enrichment):
        """Bekannter Ticker mit 3x mehr Nennungen als normal löst Spike-Alert aus."""
        from wsb_crawler.analysis.detector import analyze_mentions

        # Historische Daten einfügen (avg ≈ 10/Lauf)
        run_id = await db.start_run(["wallstreetbets"])
        await db.save_run_mentions(run_id, {"GME": 10})
        await db.finish_run(run_id, 100, 50)

        # Aktuell: 35 Nennungen = 3.5x Avg, Delta = 25 (beide Schwellen überschritten)
        alerts = await analyze_mentions({"GME": 35}, db)

        assert len(alerts) == 1
        assert alerts[0].reason == AlertReason.SPIKE
        assert alerts[0].spike.ratio >= 2.0

    async def test_cooldown_prevents_duplicate_alert(self, db: Database, mock_enrichment):
        """Ticker im Cooldown löst keinen zweiten Alert aus."""
        from wsb_crawler.analysis.detector import analyze_mentions

        # Cooldown setzen
        await db.set_cooldown("GME", hours=4)

        alerts = await analyze_mentions({"GME": 50}, db)
        assert len(alerts) == 0

    async def test_max_alerts_per_run_respected(self, db: Database, mock_enrichment):
        """Maximal 3 Alerts pro Lauf (konfigurierbar)."""
        from wsb_crawler.analysis.detector import analyze_mentions

        # Viele neue Ticker mit hohen Nennungen
        counts = {f"TICK{i}": 30 for i in range(10)}

        # Enrichment für alle Ticker patchen
        with (
            patch(
                "wsb_crawler.analysis.detector.get_prices_bulk",
                new=AsyncMock(return_value={t: None for t in counts}),
            ),
            patch(
                "wsb_crawler.analysis.detector.get_news_bulk",
                new=AsyncMock(return_value={t: [] for t in counts}),
            ),
            patch(
                "wsb_crawler.analysis.detector.resolve_names_bulk",
                new=AsyncMock(return_value={t: None for t in counts}),
            ),
        ):
            alerts = await analyze_mentions(counts, db)

        # max_per_run ist 3 (Default in config)
        assert len(alerts) <= 3

    async def test_empty_mentions_returns_no_alerts(self, db: Database, mock_enrichment):
        """Keine Mentions → keine Alerts."""
        from wsb_crawler.analysis.detector import analyze_mentions
        alerts = await analyze_mentions({}, db)
        assert alerts == []


class TestCooldownLogic:
    async def test_cooldown_set_and_active(self, db: Database):
        """Cooldown wird korrekt gesetzt."""
        assert not await db.is_on_cooldown("GME")
        await db.set_cooldown("GME", hours=4)
        assert await db.is_on_cooldown("GME")

    async def test_cooldown_expires(self, db: Database):
        """Abgelaufener Cooldown wird korrekt erkannt."""
        # Expired cooldown direkt in DB schreiben
        now = datetime.now(tz=timezone.utc)
        expired = (now - timedelta(hours=1)).isoformat()
        await db.conn.execute(
            """INSERT INTO alert_cooldowns (ticker, last_alert_at, cooldown_until)
               VALUES ('GME', ?, ?)""",
            (expired, expired),
        )
        await db.conn.commit()

        assert not await db.is_on_cooldown("GME")

    async def test_cooldown_renewal(self, db: Database):
        """Cooldown-Erneuerung erhöht den Zähler."""
        await db.set_cooldown("GME", hours=4)
        await db.set_cooldown("GME", hours=4)  # Zweites Mal

        async with db.conn.execute(
            "SELECT alert_count FROM alert_cooldowns WHERE ticker = 'GME'"
        ) as cur:
            row = await cur.fetchone()
        assert row["alert_count"] == 2
