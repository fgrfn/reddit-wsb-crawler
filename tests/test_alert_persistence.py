"""Tests für Alert-Signal-Persistierung + Spalten-Migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wsb_crawler.models import (
    Alert,
    AlertReason,
    MarketStatus,
    PriceData,
    SpikeResult,
    TickerSignal,
)
from wsb_crawler.storage.database import Database

# alte alert_history-Schema-Version (vor der Signal-Migration)
_OLD_SCHEMA = """
CREATE TABLE alert_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT NOT NULL,
    reason       TEXT NOT NULL,
    mentions     INTEGER NOT NULL,
    avg_mentions REAL NOT NULL,
    ratio        REAL NOT NULL,
    price        REAL,
    price_change REAL,
    sent_at      TEXT NOT NULL
);
"""


def _alert(*, with_signal: bool = True) -> Alert:
    spike = SpikeResult(
        ticker="GME",
        current_mentions=40,
        avg_mentions=5.0,
        ratio=8.0,
        delta=35,
        is_new=False,
        reason=AlertReason.SPIKE,
        price_data=PriceData(
            ticker="GME",
            company_name="GameStop",
            price=42.0,
            change_24h=2.0,
            market_status=MarketStatus.OPEN,
        ),
        signal=TickerSignal(
            ticker="GME",
            mention_count=40,
            total_score=8000,
            max_score=900,
            bull_hits=6,
            bear_hits=0,
        )
        if with_signal
        else None,
        confidence=86,
    )
    return Alert(ticker="GME", reason=AlertReason.SPIKE, spike=spike)


class TestMigration:
    async def test_adds_missing_columns_to_old_db(self, tmp_path: Path) -> None:
        path = tmp_path / "old.db"
        # DB mit altem Schema anlegen (ohne die Signal-Spalten)
        con = sqlite3.connect(path)
        con.executescript(_OLD_SCHEMA)
        con.commit()
        con.close()

        db = Database(path)
        await db.init()  # Migration läuft hier
        async with db.conn.execute("PRAGMA table_info(alert_history)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        await db.close()

        assert {"confidence", "sentiment", "sentiment_label", "avg_score"} <= cols

    async def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / "fresh.db"
        db = Database(path)
        await db.init()
        await db._run_column_migrations()  # zweiter Lauf darf nicht crashen
        await db.close()


class TestPersistence:
    @pytest.fixture
    async def db(self, tmp_path: Path) -> Database:
        database = Database(tmp_path / "t.db")
        await database.init()
        yield database
        await database.close()

    async def test_save_and_read_signal_fields(self, db: Database) -> None:
        await db.save_alert(_alert())
        rows = await db.get_alert_history(ticker="GME")
        assert len(rows) == 1
        row = rows[0]
        assert row["confidence"] == 86
        assert row["sentiment"] == pytest.approx(1.0)
        assert row["sentiment_label"] == "bullish"
        assert row["avg_score"] == pytest.approx(200.0)

    async def test_alert_without_signal_stores_nulls(self, db: Database) -> None:
        await db.save_alert(_alert(with_signal=False))
        row = (await db.get_alert_history(ticker="GME"))[0]
        assert row["sentiment"] is None
        assert row["sentiment_label"] is None
        assert row["avg_score"] is None
