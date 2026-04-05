"""
Tests für die Datenbankschicht (storage/database.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from wsb_crawler.storage.database import Database


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


class TestCrawlRuns:
    async def test_start_and_finish_run(self, db: Database):
        """Lauf kann gestartet und abgeschlossen werden."""
        run_id = await db.start_run(["wallstreetbets"])
        assert run_id  # nicht leer

        await db.finish_run(run_id, posts_scanned=100, comments_scanned=500)

        async with db.conn.execute(
            "SELECT * FROM crawl_runs WHERE id = ?", (run_id,)
        ) as cur:
            row = await cur.fetchone()

        assert row is not None
        assert row["posts_scanned"] == 100
        assert row["comments_scanned"] == 500
        assert row["finished_at"] is not None
        assert row["is_healthy"] == 1

    async def test_unhealthy_run_marked(self, db: Database):
        """Fehlerhafter Lauf wird als unhealthy markiert."""
        run_id = await db.start_run(["wallstreetbets"])
        await db.finish_run(run_id, 0, 0, is_healthy=False)

        async with db.conn.execute(
            "SELECT is_healthy FROM crawl_runs WHERE id = ?", (run_id,)
        ) as cur:
            row = await cur.fetchone()
        assert row["is_healthy"] == 0


class TestTickerHistory:
    async def test_save_and_retrieve_mentions(self, db: Database):
        """Mentions werden gespeichert und korrekt abgerufen."""
        run_id = await db.start_run(["wallstreetbets"])
        await db.save_run_mentions(run_id, {"GME": 42, "AMC": 17})

        history_gme = await db.get_ticker_history("GME", days=30)
        assert len(history_gme.mention_counts) == 1
        assert history_gme.mention_counts[0][1] == 42

        history_amc = await db.get_ticker_history("AMC", days=30)
        assert history_amc.mention_counts[0][1] == 17

    async def test_avg_mentions_empty(self, db: Database):
        """Durchschnitt ist 0 wenn keine History vorhanden."""
        avg = await db.get_avg_mentions("UNKNOWN", days=30)
        assert avg == 0.0

    async def test_avg_mentions_calculated(self, db: Database):
        """Durchschnitt wird korrekt berechnet."""
        for count in [10, 20, 30]:
            run_id = await db.start_run(["wsb"])
            await db.save_run_mentions(run_id, {"GME": count})

        avg = await db.get_avg_mentions("GME", days=30)
        # 3 Läufe am gleichen Tag → sum(10+20+30) = 60 auf 1 Tag → avg = 60.0
        assert avg == 60.0

    async def test_is_known_ticker(self, db: Database):
        """Bekannte vs. unbekannte Ticker werden korrekt unterschieden."""
        assert not await db.is_known_ticker("GME")

        run_id = await db.start_run(["wsb"])
        await db.save_run_mentions(run_id, {"GME": 5})

        assert await db.is_known_ticker("GME")
        assert not await db.is_known_ticker("AMC")


class TestStatus:
    async def test_run_status_empty(self, db: Database):
        """Status bei leerer DB ist sinnvoll initialisiert."""
        status = await db.get_run_status()
        assert status.last_run_at is None
        assert status.total_runs == 0
        assert status.tracked_tickers == 0
        assert status.total_alerts_sent == 0

    async def test_run_status_after_runs(self, db: Database):
        """Status spiegelt gespeicherte Läufe korrekt wider."""
        for _ in range(3):
            run_id = await db.start_run(["wsb"])
            await db.save_run_mentions(run_id, {"GME": 10})
            await db.finish_run(run_id, 100, 50)

        status = await db.get_run_status()
        assert status.total_runs == 3
        assert status.tracked_tickers == 1
        assert status.last_run_at is not None
