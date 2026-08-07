"""Tests für konfigurierbare @-Erwähnungen bei Discord-Alerts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from wsb_crawler.alerts import discord
from wsb_crawler.alerts.discord import build_mentions
from wsb_crawler.config import (
    AlertSettings,
    CrawlerSettings,
    DiscordSettings,
    NewsAPISettings,
    RedditSettings,
    Settings,
)
from wsb_crawler.models import Alert, AlertReason, SpikeResult


def _settings(mention_targets: str | None) -> Settings:
    return Settings(
        reddit=RedditSettings(client_id="a", client_secret="b"),
        newsapi=NewsAPISettings(key="k"),
        discord=DiscordSettings(
            webhook_url="https://discord.com/api/webhooks/1/x",
            mention_targets=mention_targets,
        ),
        alerts=AlertSettings(),
        crawler=CrawlerSettings(),
    )


class TestBuildMentions:
    def test_empty_returns_no_mentions(self) -> None:
        assert build_mentions(None) == ("", None)
        assert build_mentions("") == ("", None)
        assert build_mentions("   ") == ("", None)

    def test_plain_user_id(self) -> None:
        content, allowed = build_mentions("123456789012345678")
        assert content == "<@123456789012345678>"
        assert allowed == {"users": ["123456789012345678"]}

    def test_role_prefixes(self) -> None:
        content, allowed = build_mentions("&987, role:654")
        assert content == "<@&987> <@&654>"
        assert allowed == {"roles": ["987", "654"]}

    def test_here_and_everyone(self) -> None:
        content, allowed = build_mentions("@here")
        assert content == "@here"
        assert allowed == {"parse": ["everyone"]}
        content, allowed = build_mentions("everyone")
        assert content == "@everyone"
        assert allowed == {"parse": ["everyone"]}

    def test_preformatted_mentions(self) -> None:
        content, allowed = build_mentions("<@111> <@!222> <@&333>")
        assert content == "<@111> <@222> <@&333>"
        assert allowed == {"users": ["111", "222"], "roles": ["333"]}

    def test_mixed_and_separators(self) -> None:
        content, allowed = build_mentions("123, &456 @here")
        assert content == "<@123> <@&456> @here"
        assert allowed == {"parse": ["everyone"], "users": ["123"], "roles": ["456"]}

    def test_deduplicates(self) -> None:
        content, allowed = build_mentions("123 123 <@123>")
        assert content == "<@123>"
        assert allowed == {"users": ["123"]}

    def test_ignores_unknown_tokens(self) -> None:
        content, allowed = build_mentions("hello world @someuser")
        assert content == ""
        assert allowed is None


def _alert() -> Alert:
    spike = SpikeResult(
        ticker="GME",
        current_mentions=40,
        avg_mentions=5.0,
        ratio=8.0,
        delta=35,
        is_new=False,
        reason=AlertReason.SPIKE,
    )
    return Alert(ticker="GME", reason=AlertReason.SPIKE, spike=spike)


class TestSendAlertWiring:
    async def test_payload_includes_mentions_when_configured(self) -> None:
        captured: dict = {}

        async def _fake_send(payload, webhook_url, **kwargs):
            captured.update(payload)
            return True

        with (
            patch.object(discord, "_get_db", return_value=MagicMock()),
            patch.object(
                discord, "get_settings", new=AsyncMock(return_value=_settings("123 @here"))
            ),
            patch.object(discord, "_send_webhook", new=_fake_send),
        ):
            ok = await discord.send_alert(_alert())

        assert ok is True
        assert captured["content"] == "<@123> @here"
        assert captured["allowed_mentions"] == {"parse": ["everyone"], "users": ["123"]}

    async def test_no_content_key_when_unset(self) -> None:
        captured: dict = {}

        async def _fake_send(payload, webhook_url, **kwargs):
            captured.update(payload)
            return True

        with (
            patch.object(discord, "_get_db", return_value=MagicMock()),
            patch.object(discord, "get_settings", new=AsyncMock(return_value=_settings(None))),
            patch.object(discord, "_send_webhook", new=_fake_send),
        ):
            await discord.send_alert(_alert())

        assert "content" not in captured
        assert "allowed_mentions" not in captured
