"""
Tests für die Trend-Berechnung (analysis/trends.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wsb_crawler.analysis.trends import _calculate_trend, get_top_tickers_cached
from wsb_crawler.models import MarketStatus, PriceData, TickerHistory, TrendDirection
from wsb_crawler.storage.cache import name_cache, price_cache
from wsb_crawler.storage.database import Database


def _history(values: list[int]) -> TickerHistory:
    base = datetime.now(tz=UTC)
    counts = [(base + timedelta(days=i), v) for i, v in enumerate(values)]
    return TickerHistory(ticker="GME", mention_counts=counts)


class TestCalculateTrend:
    def test_too_few_points_is_flat(self):
        assert _calculate_trend(_history([1, 2])) == TrendDirection.FLAT

    def test_rising_trend(self):
        # ältere 4 Tage niedrig, letzte 3 Tage deutlich höher
        assert _calculate_trend(_history([1, 1, 1, 1, 10, 10, 10])) == TrendDirection.UP

    def test_falling_trend(self):
        assert _calculate_trend(_history([10, 10, 10, 10, 1, 1, 1])) == TrendDirection.DOWN

    def test_flat_trend(self):
        assert _calculate_trend(_history([5, 5, 5, 5, 5, 5, 5])) == TrendDirection.FLAT

    def test_from_zero_base_is_up(self):
        # ältere Werte 0 → jede Steigerung ist UP
        assert _calculate_trend(_history([0, 0, 0, 0, 3, 4, 5])) == TrendDirection.UP


class TestTopTickersCached:
    @pytest.fixture
    async def db(self, tmp_path: Path) -> Database:
        database = Database(tmp_path / "t.db")
        await database.init()
        yield database
        await database.close()

    async def test_network_free_enrichment(self, db: Database):
        """Trend kommt aus der DB, Kurs/Name nur aus dem Cache — kein Netzwerk."""
        price_cache.clear()
        name_cache.clear()
        # 7 Tage History mit klarem Anstieg → Trend UP.
        # save_run_mentions setzt recorded_at=now, daher danach zurückdatieren.
        base = datetime.now(tz=UTC)
        for i, v in enumerate([1, 1, 1, 1, 10, 10, 20]):
            run_id = await db.start_run(["wsb"])
            await db.save_run_mentions(run_id, {"GME": v})
            await db.conn.execute(
                "UPDATE ticker_mentions SET recorded_at = ? WHERE run_id = ?",
                ((base - timedelta(days=6 - i)).isoformat(), run_id),
            )
        await db.conn.commit()

        # Kurs im Cache → wird übernommen; Name fehlt → None
        price_cache.set(
            "GME",
            PriceData(
                ticker="GME",
                company_name="GameStop",
                price=42.0,
                change_7d=5.0,
                market_status=MarketStatus.OPEN,
            ),
        )

        entries = await get_top_tickers_cached(db, days=7, limit=10)
        gme = next(e for e in entries if e.ticker == "GME")
        assert gme.trend_direction == TrendDirection.UP
        assert gme.current_price == 42.0
        assert gme.price_change_period == 5.0
        assert gme.company_name is None  # nicht im Cache → nicht-blockierend None
