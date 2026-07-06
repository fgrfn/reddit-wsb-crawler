"""
Tests für den In-Memory TTL-Cache (storage/cache.py).
"""

from __future__ import annotations

import time
from unittest.mock import patch

from wsb_crawler.storage.cache import TTLCache


class TestTTLCache:
    def test_set_and_get(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=300)
        cache.set("GME", "GameStop")
        assert cache.get("GME") == "GameStop"

    def test_missing_key_returns_none(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=300)
        assert cache.get("UNKNOWN") is None

    def test_expired_entry_returns_none(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=300)
        cache.set("GME", "GameStop")
        # Zeit künstlich vorspulen (TTL überschreiten)
        with patch("wsb_crawler.storage.cache.time.monotonic", return_value=time.monotonic() + 400):
            assert cache.get("GME") is None

    def test_invalidate_removes_entry(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=300)
        cache.set("GME", "GameStop")
        cache.invalidate("GME")
        assert cache.get("GME") is None

    def test_clear_empties_cache(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=300)
        cache.set("GME", "GameStop")
        cache.set("AMC", "AMC Entertainment")
        cache.clear()
        assert len(cache) == 0

    def test_len_evicts_expired(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=300)
        cache.set("GME", "GameStop")
        assert len(cache) == 1
        with patch("wsb_crawler.storage.cache.time.monotonic", return_value=time.monotonic() + 400):
            assert len(cache) == 0

    def test_stats_reports_size_and_ttl(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=123)
        cache.set("GME", "GameStop")
        stats = cache.stats
        assert stats["size"] == 1
        assert stats["ttl_seconds"] == 123
