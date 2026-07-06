"""
Tests für News-Enrichment (enrichment/news.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wsb_crawler.enrichment import news as news_mod
from wsb_crawler.storage.cache import news_cache
from wsb_crawler.storage.database import Database


@pytest.fixture(autouse=True)
def _clear_cache():
    news_cache.clear()
    yield
    news_cache.clear()


async def _seed_required(database: Database) -> None:
    """get_settings() verlangt die Reddit-/Discord-Pflichtfelder."""
    await database.set_setting("reddit_client_id", "test_id")
    await database.set_setting("reddit_client_secret", "test_secret")
    await database.set_setting("discord_webhook_url", "https://discord.com/api/webhooks/0/test")


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.init()
    await _seed_required(database)
    await database.set_setting("newsapi_key", "test_key")
    news_mod.set_database(database)
    yield database
    await database.close()


_ARTICLE = {
    "title": "GameStop soars",
    "source": {"name": "Reuters"},
    "url": "https://example.com/gme",
    "publishedAt": "2026-01-01T12:00:00Z",
}


class TestGetNews:
    async def test_parses_articles(self, db: Database):
        with patch.object(news_mod, "_fetch_articles", new=AsyncMock(return_value=[_ARTICLE])):
            articles = await news_mod.get_news("GME", company_name="GameStop Corp.")
        assert len(articles) == 1
        assert articles[0].title == "GameStop soars"
        assert articles[0].source == "Reuters"

    async def test_no_api_key_returns_empty(self, tmp_path: Path):
        database = Database(tmp_path / "nokey.db")
        await database.init()
        await _seed_required(database)  # alles außer newsapi_key
        news_mod.set_database(database)
        try:
            assert await news_mod.get_news("GME") == []
        finally:
            await database.close()

    async def test_error_returns_empty_and_caches(self, db: Database):
        with patch.object(
            news_mod, "_fetch_articles", new=AsyncMock(side_effect=RuntimeError("boom"))
        ) as mock_fetch:
            assert await news_mod.get_news("GME") == []
            # Zweiter Aufruf kommt aus dem (leeren) Cache → kein zweiter Fetch
            assert await news_mod.get_news("GME") == []
            assert mock_fetch.call_count == 1

    async def test_bulk_passes_company_names(self, db: Database):
        with patch.object(news_mod, "_fetch_articles", new=AsyncMock(return_value=[])):
            result = await news_mod.get_news_bulk(["GME"], company_names={"GME": "GameStop"})
        assert result == {"GME": []}
