"""
Tests für die Datenmodelle (models.py).
"""

from datetime import datetime, timezone

import pytest

from wsb_crawler.models import (
    CrawlResult,
    MarketStatus,
    PriceData,
    TickerHistory,
    TrendDirection,
)


class TestPriceData:
    def _price(self, **kwargs) -> PriceData:
        return PriceData(ticker="GME", company_name="GameStop", price=42.0, **kwargs)

    def test_primary_price_open_market(self):
        p = self._price(market_status=MarketStatus.OPEN)
        assert p.primary_price == 42.0

    def test_primary_price_pre_market(self):
        p = self._price(
            market_status=MarketStatus.PRE_MARKET,
            pre_market_price=45.0,
        )
        assert p.primary_price == 45.0

    def test_primary_price_after_hours(self):
        p = self._price(
            market_status=MarketStatus.AFTER_HOURS,
            after_hours_price=40.0,
        )
        assert p.primary_price == 40.0

    def test_primary_change_uses_24h_when_open(self):
        p = self._price(market_status=MarketStatus.OPEN, change_24h=5.5)
        assert p.primary_change == 5.5

    def test_primary_change_pre_market_fallback(self):
        """Kein Pre-Market Change → fällt auf 24h zurück."""
        p = self._price(
            market_status=MarketStatus.PRE_MARKET,
            pre_market_change=None,
            change_24h=3.0,
        )
        assert p.primary_change == 3.0


class TestCrawlResult:
    def _result(self) -> CrawlResult:
        started = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        finished = datetime(2024, 1, 1, 10, 1, 30, tzinfo=timezone.utc)
        return CrawlResult(
            run_id="test-run",
            started_at=started,
            finished_at=finished,
            mention_counts={"GME": 50, "AMC": 30, "TSLA": 10},
        )

    def test_duration_calculated(self):
        r = self._result()
        assert r.duration_seconds == 90.0

    def test_duration_none_when_not_finished(self):
        r = CrawlResult(run_id="x", started_at=datetime.now(tz=timezone.utc))
        assert r.duration_seconds is None

    def test_top_tickers_sorted(self):
        r = self._result()
        top = r.top_tickers
        assert top[0] == ("GME", 50)
        assert top[1] == ("AMC", 30)
        assert top[2] == ("TSLA", 10)


class TestTickerHistory:
    def _history(self, counts: list[int]) -> TickerHistory:
        now = datetime.now(tz=timezone.utc)
        return TickerHistory(
            ticker="GME",
            mention_counts=[(now, c) for c in counts],
        )

    def test_avg_mentions_calculated(self):
        h = self._history([10, 20, 30])
        assert h.avg_mentions == 20.0

    def test_avg_mentions_empty(self):
        h = self._history([])
        assert h.avg_mentions == 0.0

    def test_trend_up(self):
        # Erste 4 niedrig, letzte 3 hoch
        h = self._history([5, 5, 5, 5, 50, 60, 70])
        assert h.trend_direction == TrendDirection.UP

    def test_trend_down(self):
        h = self._history([50, 60, 70, 80, 5, 5, 5])
        assert h.trend_direction == TrendDirection.DOWN

    def test_trend_flat(self):
        h = self._history([20, 22, 21, 20, 21, 22, 20])
        assert h.trend_direction == TrendDirection.FLAT

    def test_trend_insufficient_data(self):
        h = self._history([10, 20])
        assert h.trend_direction == TrendDirection.FLAT
