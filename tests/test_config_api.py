"""
Tests für den Config-Router (api/routers/config.py).

Ruft die Endpoint-Funktionen direkt auf (kein HTTP-Server nötig) und setzt
die Modul-Level-DB wie server.py::set_database es tut.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from wsb_crawler.api.routers import config as config_router
from wsb_crawler.api.routers.config import MASK, ConfigPayload
from wsb_crawler.storage.database import Database


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.init()
    config_router.db = database
    yield database
    await database.close()


class TestConfigMasking:
    async def test_secrets_are_masked(self, db: Database):
        await db.set_setting("reddit_client_secret", "supersecret")
        await db.set_setting("discord_webhook_url", "https://discord.com/api/webhooks/1/abc")
        await db.set_setting("reddit_client_id", "public_id")

        result = await config_router.get_config()

        assert result["reddit_client_secret"] == MASK
        # Webhook-URL ist ein Credential → ebenfalls maskiert
        assert result["discord_webhook_url"] == MASK
        # Nicht-Secrets bleiben im Klartext
        assert result["reddit_client_id"] == "public_id"

    async def test_masked_placeholder_not_written_back(self, db: Database):
        await db.set_setting("reddit_client_secret", "original")

        # UI schickt den maskierten Platzhalter zurück → darf nicht überschreiben
        await config_router.update_config(ConfigPayload(reddit_client_secret=MASK))

        assert await db.get_setting("reddit_client_secret") == "original"

    async def test_update_persists_and_strips(self, db: Database):
        await config_router.update_config(ConfigPayload(reddit_client_id="  padded_id  "))
        assert await db.get_setting("reddit_client_id") == "padded_id"

    async def test_config_status_reflects_configuration(self, db: Database):
        assert (await config_router.config_status())["configured"] is False
        await db.set_setting("reddit_client_id", "x")
        await db.set_setting("reddit_client_secret", "y")
        await db.set_setting("discord_webhook_url", "https://discord.com/api/webhooks/1/z")
        assert (await config_router.config_status())["configured"] is True


class TestConfigValidation:
    def test_webhook_url_must_be_discord(self):
        with pytest.raises(ValidationError):
            ConfigPayload(discord_webhook_url="https://evil.example/webhook")

    def test_valid_webhook_url_accepted(self):
        payload = ConfigPayload(discord_webhook_url="https://discord.com/api/webhooks/1/abc")
        assert payload.discord_webhook_url is not None

    def test_crawl_interval_must_be_positive(self):
        with pytest.raises(ValidationError):
            ConfigPayload(crawl_interval_minutes=0)

    def test_posts_limit_upper_bound(self):
        with pytest.raises(ValidationError):
            ConfigPayload(posts_limit=5000)

    def test_alert_ratio_must_be_positive(self):
        with pytest.raises(ValidationError):
            ConfigPayload(alert_ratio=0)
