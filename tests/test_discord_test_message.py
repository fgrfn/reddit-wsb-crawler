"""Tests für die Discord-Testnachricht (erfundener Beispiel-Alert)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from wsb_crawler.api.routers import config as config_router
from wsb_crawler.config import (
    AlertSettings,
    CrawlerSettings,
    DiscordSettings,
    NewsAPISettings,
    RedditSettings,
    Settings,
)


def _settings(mention_targets: str | None = None) -> Settings:
    return Settings(
        reddit=RedditSettings("a", "b"),
        newsapi=NewsAPISettings(key="k"),
        discord=DiscordSettings(
            webhook_url="https://discord.com/api/webhooks/1/x",
            mention_targets=mention_targets,
        ),
        alerts=AlertSettings(),
        crawler=CrawlerSettings(subreddits=["wallstreetbets"]),
    )


class TestDemoAlert:
    def test_demo_alert_is_complete_enough_to_render(self) -> None:
        alert = config_router._demo_alert()
        assert alert.spike.price_data is not None
        assert alert.spike.signal is not None
        assert alert.spike.news  # eine Beispiel-Schlagzeile
        assert alert.spike.confidence > 0

    def test_demo_isin_is_a_placeholder_not_a_real_looking_one(self) -> None:
        from wsb_crawler.enrichment.isin import is_valid_isin

        # Die Testnachricht lädt zum Kopieren in die Broker-Suche ein — ein
        # ISIN-artiger Wert könnte dort ein echtes, falsches Papier treffen
        placeholder = config_router._demo_alert().spike.isin
        assert placeholder  # die Zeile erscheint …
        assert not is_valid_isin(placeholder)  # … aber nicht als ISIN lesbar


class TestTestMessage:
    async def _send(self, mention_targets: str | None = None) -> dict:
        captured: dict = {}

        async def _fake_send(payload, webhook_url, **kwargs):
            captured.update(payload)
            return True

        with (
            patch.object(config_router, "is_configured", new=AsyncMock(return_value=True)),
            patch.object(
                config_router,
                "get_settings",
                new=AsyncMock(return_value=_settings(mention_targets)),
            ),
            patch.object(config_router, "_send_webhook", new=_fake_send),
        ):
            result = await config_router.test_discord_webhook()
        assert result == {"ok": True}
        return captured

    async def test_sends_a_realistic_example_alert(self) -> None:
        payload = await self._send()
        embed = payload["embeds"][0]
        # Als Test erkennbar, aber inhaltlich ein echter Alert
        assert embed["title"].startswith("🧪 Testnachricht")
        assert "$DEMO" in embed["title"]
        assert "erfundenen Daten" in embed["footer"]["text"]
        names = [f["name"] for f in embed["fields"]]
        assert "Was ist passiert?" in names
        assert "📊 Nennungen" in names
        assert "💰 Kurs" in names
        # Die ISIN-Zeile gehört dazu, sonst zeigt der Test nicht, wie ein Alert aussieht
        assert any("ISIN" in name for name in names)

    async def test_never_pings_even_with_targets_configured(self) -> None:
        payload = await self._send("123456789012345678, @here")
        assert payload["allowed_mentions"] == {"parse": []}
        assert "content" not in payload
        # Die Ziele werden nur benannt
        field = next(f for f in payload["embeds"][0]["fields"] if f["name"].startswith("🔔"))
        assert "<@123456789012345678>" in field["value"]
        assert "@here" in field["value"]

    async def test_states_when_no_targets_configured(self) -> None:
        payload = await self._send(None)
        field = next(f for f in payload["embeds"][0]["fields"] if f["name"].startswith("🔔"))
        assert "niemand" in field["value"]

    async def test_unconfigured_system_is_rejected(self) -> None:
        from fastapi import HTTPException

        with (
            patch.object(config_router, "is_configured", new=AsyncMock(return_value=False)),
            pytest.raises(HTTPException) as exc,
        ):
            await config_router.test_discord_webhook()
        assert exc.value.status_code == 400

    async def test_webhook_failure_surfaces_as_502(self) -> None:
        from fastapi import HTTPException

        with (
            patch.object(config_router, "is_configured", new=AsyncMock(return_value=True)),
            patch.object(config_router, "get_settings", new=AsyncMock(return_value=_settings())),
            patch.object(config_router, "_send_webhook", new=AsyncMock(return_value=False)),
            pytest.raises(HTTPException) as exc,
        ):
            await config_router.test_discord_webhook()
        assert exc.value.status_code == 502
