"""Tests für robusten Kursabruf: fehlende Felder, Rate-Limit, Alphavantage-Fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from wsb_crawler.enrichment import prices
from wsb_crawler.enrichment.prices import (
    RateLimitedError,
    _fast_info_value,
    _is_rate_limited,
)
from wsb_crawler.models import PriceData


@pytest.fixture(autouse=True)
def _clean_caches():
    """Kurs- und Negativ-Cache zwischen Tests leeren (Modul-globaler Zustand)."""
    prices._failed_price_cache.clear()
    prices.price_cache.clear()
    yield
    prices._failed_price_cache.clear()
    prices.price_cache.clear()


class _RaisingInfo:
    """fast_info-Attrappe, die für bestimmte Felder KeyError wirft."""

    def __init__(self, data: dict, raising: set[str]) -> None:
        self._data = data
        self._raising = raising

    def get(self, key: str, default=None):  # noqa: ANN001, ANN202
        if key in self._raising:
            raise KeyError(key)
        return self._data.get(key, default)


class TestFastInfoValue:
    def test_missing_field_falls_back_to_default(self) -> None:
        info = _RaisingInfo({"last_price": 10.0}, raising={"currency"})
        # Genau der Fehler aus dem Log: KeyError 'currency'
        assert _fast_info_value(info, "currency", "USD") == "USD"
        assert _fast_info_value(info, "last_price") == 10.0

    def test_none_value_uses_default(self) -> None:
        info = _RaisingInfo({"currency": None}, raising=set())
        assert _fast_info_value(info, "currency", "USD") == "USD"

    def test_unknown_key_uses_default(self) -> None:
        info = _RaisingInfo({}, raising=set())
        assert _fast_info_value(info, "market_cap") is None


class TestRateLimitDetection:
    @pytest.mark.parametrize(
        "message",
        [
            "429 Client Error: Too Many Requests for url: ...",
            "Too Many Requests",
            "HTTP 429",
        ],
    )
    def test_detects_rate_limit(self, message: str) -> None:
        assert _is_rate_limited(RuntimeError(message))

    def test_other_errors_are_not_rate_limits(self) -> None:
        assert not _is_rate_limited(RuntimeError("'currency'"))
        assert not _is_rate_limited(ValueError("possibly delisted"))


class TestAlphavantageFallback:
    @staticmethod
    def _quote(price: str = "24.80", change: str = "6.4000%") -> dict:
        return {"Global Quote": {"05. price": price, "10. change percent": change}}

    async def _fetch(self, payload: dict, *, key: str | None = "KEY") -> PriceData | None:
        class _Resp:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return payload

        client = AsyncMock()
        client.__aenter__.return_value.get = AsyncMock(return_value=_Resp())
        with (
            patch.object(prices, "_alphavantage_key", new=AsyncMock(return_value=key)),
            patch.object(prices.httpx, "AsyncClient", return_value=client),
        ):
            return await prices._fetch_price_alphavantage("HTZ")

    async def test_parses_price_and_change(self) -> None:
        data = await self._fetch(self._quote())
        assert data is not None
        assert data.price == pytest.approx(24.80)
        assert data.change_24h == pytest.approx(6.4)  # "%" wird entfernt

    async def test_without_key_it_is_skipped(self) -> None:
        assert await self._fetch(self._quote(), key=None) is None

    async def test_empty_quote_returns_none(self) -> None:
        assert await self._fetch({"Global Quote": {}}) is None

    async def test_rate_limit_note_disables_fallback(self) -> None:
        assert await self._fetch({"Note": "call frequency limit"}) is None
        # Kontingent wird nicht weiter verbrannt
        assert prices._negative_cache_hit(prices._ALPHAVANTAGE_COOLDOWN_KEY)


class TestGetPriceFallbackWiring:
    async def test_falls_back_when_yfinance_raises(self) -> None:
        fallback = PriceData(ticker="HTZ", company_name=None, price=6.42)
        with (
            patch.object(
                prices,
                "_fetch_price_with_retry",
                new=AsyncMock(side_effect=RateLimitedError("429")),
            ),
            patch.object(prices, "_fetch_price_alphavantage", new=AsyncMock(return_value=fallback)),
        ):
            data = await prices.get_price("HTZ")
        assert data is not None
        assert data.price == pytest.approx(6.42)

    async def test_falls_back_when_yfinance_returns_no_price(self) -> None:
        # Der "possibly delisted"-Fall: Abruf klappt, Kurs fehlt trotzdem
        empty = PriceData(ticker="WEN", company_name=None, price=None)
        fallback = PriceData(ticker="WEN", company_name=None, price=12.5)
        with (
            patch.object(prices, "_fetch_price_with_retry", new=AsyncMock(return_value=empty)),
            patch.object(
                prices, "_fetch_price_alphavantage", new=AsyncMock(return_value=fallback)
            ) as av,
        ):
            data = await prices.get_price("WEN")
        av.assert_awaited_once()
        assert data is not None
        assert data.price == pytest.approx(12.5)

    async def test_returns_none_when_both_sources_fail(self) -> None:
        with (
            patch.object(
                prices, "_fetch_price_with_retry", new=AsyncMock(side_effect=RuntimeError("boom"))
            ),
            patch.object(prices, "_fetch_price_alphavantage", new=AsyncMock(return_value=None)),
        ):
            assert await prices.get_price("XYZ") is None
        # Negativer Cache verhindert Dauer-Retry im selben Lauf
        assert prices._negative_cache_hit("XYZ")

    async def test_no_fallback_call_when_yfinance_succeeds(self) -> None:
        good = PriceData(ticker="GME", company_name=None, price=42.0)
        with (
            patch.object(prices, "_fetch_price_with_retry", new=AsyncMock(return_value=good)),
            patch.object(prices, "_fetch_price_alphavantage", new=AsyncMock()) as av,
        ):
            data = await prices.get_price("GME")
        assert data is not None
        av.assert_not_awaited()  # Kontingent der Zweitquelle wird geschont
