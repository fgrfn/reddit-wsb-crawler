"""
Tests für die Datenbankschicht (storage/database.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wsb_crawler.storage.database import Database


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


class TestDatabaseOpen:
    async def test_clear_error_on_unwritable_path(self, tmp_path: Path):
        """Nicht öffenbarer Pfad → klare RuntimeError mit WSB_DB_PATH-Hinweis
        statt rohem sqlite3-Traceback."""
        # Datei als vermeintliches Elternverzeichnis → mkdir/connect scheitert
        afile = tmp_path / "afile"
        afile.write_text("x")
        with pytest.raises(RuntimeError, match="WSB_DB_PATH"):
            await Database(afile / "data" / "wsb.db").init()

    async def test_creates_nested_parent_dirs(self, tmp_path: Path):
        """Verschachteltes Zielverzeichnis wird angelegt."""
        database = Database(tmp_path / "a" / "b" / "wsb.db")
        await database.init()
        assert (tmp_path / "a" / "b" / "wsb.db").exists()
        await database.close()


class TestCrawlRuns:
    async def test_start_and_finish_run(self, db: Database):
        """Lauf kann gestartet und abgeschlossen werden."""
        run_id = await db.start_run(["wallstreetbets"])
        assert run_id  # nicht leer

        await db.finish_run(run_id, posts_scanned=100, comments_scanned=500)

        async with db.conn.execute("SELECT * FROM crawl_runs WHERE id = ?", (run_id,)) as cur:
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


class TestRetention:
    async def test_purge_old_mentions(self, db: Database):
        """Mentions älter als N Tage werden gelöscht, neuere bleiben."""
        old_run = await db.start_run(["wsb"])
        await db.save_run_mentions(old_run, {"GME": 5})
        # Alten Eintrag künstlich zurückdatieren
        await db.conn.execute(
            "UPDATE ticker_mentions SET recorded_at = '2000-01-01T00:00:00+00:00' WHERE run_id = ?",
            (old_run,),
        )
        await db.conn.commit()

        new_run = await db.start_run(["wsb"])
        await db.save_run_mentions(new_run, {"AMC": 3})

        deleted = await db.purge_old_mentions(days=90)

        assert deleted == 1
        assert not await db.is_known_ticker("GME")
        assert await db.is_known_ticker("AMC")

    async def test_get_avg_mentions_excludes_run(self, db: Database):
        """exclude_run_id blendet den aktuellen Lauf aus der Durchschnittsberechnung aus."""
        run_id = await db.start_run(["wsb"])
        await db.save_run_mentions(run_id, {"GME": 50})

        # Ohne Ausschluss zählt der Lauf mit → avg = 50
        assert await db.get_avg_mentions("GME", days=30) == 50.0
        # Mit Ausschluss bleibt keine History → avg = 0
        assert await db.get_avg_mentions("GME", days=30, exclude_run_id=run_id) == 0.0


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
