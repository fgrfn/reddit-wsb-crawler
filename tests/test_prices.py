"""
Tests für Kurs-Enrichment-Helfer (enrichment/prices.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from wsb_crawler.enrichment.prices import (
    _determine_market_status,
    _safe_float,
    get_price,
    get_prices_bulk,
)
from wsb_crawler.models import MarketStatus, PriceData
from wsb_crawler.storage.cache import price_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    price_cache.clear()
    yield
    price_cache.clear()


class TestMarketStatus:
    def test_pre_market(self):
        assert _determine_market_status({"marketState": "PRE"}) == MarketStatus.PRE_MARKET

    def test_open(self):
        assert _determine_market_status({"marketState": "REGULAR"}) == MarketStatus.OPEN

    def test_after_hours(self):
        assert _determine_market_status({"marketState": "POST"}) == MarketStatus.AFTER_HOURS

    def test_closed_default(self):
        assert _determine_market_status({}) == MarketStatus.CLOSED


class TestSafeFloat:
    def test_valid(self):
        assert _safe_float("3.14") == 3.14

    def test_none(self):
        assert _safe_float(None) is None

    def test_nan(self):
        assert _safe_float(float("nan")) is None

    def test_garbage(self):
        assert _safe_float("not-a-number") is None


class TestGetPrice:
    async def test_returns_none_on_error(self):
        with patch(
            "wsb_crawler.enrichment.prices._fetch_price_with_retry",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            assert await get_price("GME") is None

    async def test_uses_cache(self):
        data = PriceData(ticker="GME", company_name="GameStop", price=42.0)
        price_cache.set("GME", data)
        # Kein Fetch nötig — kommt aus dem Cache
        result = await get_price("GME")
        assert result is data

    async def test_bulk(self):
        data = PriceData(ticker="GME", company_name="GameStop", price=42.0)
        with patch(
            "wsb_crawler.enrichment.prices.get_price",
            new=AsyncMock(return_value=data),
        ):
            result = await get_prices_bulk(["GME", "AMC"])
        assert set(result.keys()) == {"GME", "AMC"}
