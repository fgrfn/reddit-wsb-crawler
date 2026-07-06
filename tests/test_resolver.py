"""
Tests für den Ticker-Namens-Resolver (enrichment/resolver.py).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from wsb_crawler.enrichment.resolver import resolve_name, resolve_names_bulk
from wsb_crawler.storage.cache import name_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    name_cache.clear()
    yield
    name_cache.clear()


class TestResolveName:
    async def test_resolves_via_yfinance(self):
        with patch(
            "wsb_crawler.enrichment.resolver._resolve_sync",
            return_value="GameStop Corp.",
        ):
            assert await resolve_name("GME") == "GameStop Corp."

    async def test_unknown_returns_none(self):
        with patch("wsb_crawler.enrichment.resolver._resolve_sync", return_value=None):
            assert await resolve_name("ZZZZ") is None

    async def test_result_is_cached(self):
        with patch(
            "wsb_crawler.enrichment.resolver._resolve_sync",
            return_value="GameStop Corp.",
        ) as mock_sync:
            await resolve_name("GME")
            await resolve_name("GME")
            # Zweiter Aufruf kommt aus dem Cache
            assert mock_sync.call_count == 1

    async def test_bulk(self):
        with patch(
            "wsb_crawler.enrichment.resolver._resolve_sync",
            side_effect=lambda t: {"GME": "GameStop", "AMC": "AMC Ent."}.get(t),
        ):
            result = await resolve_names_bulk(["GME", "AMC"])
        assert result == {"GME": "GameStop", "AMC": "AMC Ent."}
