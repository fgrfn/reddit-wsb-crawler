"""
Tests für die Trend-Berechnung (analysis/trends.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from wsb_crawler.analysis.trends import _calculate_trend
from wsb_crawler.models import TickerHistory, TrendDirection


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
