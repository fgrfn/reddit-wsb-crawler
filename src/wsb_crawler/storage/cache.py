"""
Einfacher In-Memory TTL-Cache.

Verhindert doppelte API-Calls wenn ein Ticker mehrfach pro Run auftaucht
(z.B. 15x $GME → yfinance wird trotzdem nur einmal gefragt).

Bewusst simpel gehalten: kein Redis, kein externes Cache-System.
Der Cache lebt nur für die Laufzeit des Prozesses.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float   # Unix timestamp


class TTLCache(Generic[T]):
    """
    Thread-safe In-Memory Cache mit TTL (Time-To-Live).

    Beispiel:
        cache: TTLCache[PriceData] = TTLCache(ttl_seconds=300)
        cache.set("GME", price_data)
        data = cache.get("GME")   # None wenn abgelaufen
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, _CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: T) -> None:
        self._store[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + self._ttl,
        )

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        self._evict_expired()
        return len(self._store)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now > v.expires_at]
        for k in expired:
            del self._store[k]

    @property
    def stats(self) -> dict[str, int]:
        self._evict_expired()
        return {"size": len(self._store), "ttl_seconds": self._ttl}


# ── Globale Cache-Instanzen ────────────────────────────────────────────────
# Werden in den Enrichment-Modulen importiert.

from wsb_crawler.models import PriceData, NewsArticle  # noqa: E402

# Kursdaten: 5 Minuten TTL (Börse ändert sich, aber nicht jede Sekunde)
price_cache: TTLCache[PriceData] = TTLCache(ttl_seconds=300)

# News: 30 Minuten TTL (Headlines ändern sich selten)
news_cache: TTLCache[list[NewsArticle]] = TTLCache(ttl_seconds=1800)

# Ticker-Namen (Firmenname zu $GME): 24h TTL (sehr stabil)
name_cache: TTLCache[str | None] = TTLCache(ttl_seconds=86_400)
