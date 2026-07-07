"""Tests für den Telegram-Alert-Kanal und den Dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from wsb_crawler.alerts import telegram
from wsb_crawler.alerts.telegram import _build_message
from wsb_crawler.config import (
    AlertSettings,
    CrawlerSettings,
    DiscordSettings,
    NewsAPISettings,
    RedditSettings,
    Settings,
    TelegramSettings,
)
from wsb_crawler.models import (
    Alert,
    AlertReason,
    MarketStatus,
    PriceData,
    SpikeResult,
    TickerSignal,
)


def _settings(*, tg_token: str | None = None, tg_chat: str | None = None) -> Settings:
    return Settings(
        reddit=RedditSettings("i", "s", "ua"),
        newsapi=NewsAPISettings(key=""),
        discord=DiscordSettings("https://discord.com/api/webhooks/1/x"),
        alerts=AlertSettings(),
        crawler=CrawlerSettings(),
        telegram=TelegramSettings(bot_token=tg_token, chat_id=tg_chat),
    )


def _alert() -> Alert:
    spike = SpikeResult(
        ticker="GME",
        current_mentions=40,
        avg_mentions=5.0,
        ratio=8.0,
        delta=35,
        is_new=False,
        reason=AlertReason.SPIKE,
        price_data=PriceData(
            ticker="GME",
            company_name="GameStop Corp.",
            price=42.0,
            change_24h=2.0,
            market_status=MarketStatus.OPEN,
        ),
        signal=TickerSignal(
            ticker="GME",
            mention_count=40,
            total_score=4000,
            max_score=900,
            bull_hits=6,
            bear_hits=0,
        ),
    )
    return Alert(ticker="GME", reason=AlertReason.SPIKE, spike=spike)


class TestEnabled:
    def test_disabled_without_token_or_chat(self) -> None:
        assert not _settings().telegram.enabled
        assert not _settings(tg_token="t").telegram.enabled
        assert not _settings(tg_chat="c").telegram.enabled

    def test_enabled_with_both(self) -> None:
        assert _settings(tg_token="t", tg_chat="c").telegram.enabled


class TestBuildMessage:
    def test_contains_key_fields(self) -> None:
        msg = _build_message(_alert())
        assert "$GME" in msg
        assert "GameStop Corp." in msg
        assert "🐂 Bullish" in msg
        assert "8.0×" in msg
        assert "$42.00" in msg


class TestSendAlert:
    async def test_skips_when_disabled(self) -> None:
        # Kein Netzwerk, kein Token → False, kein POST
        with patch("wsb_crawler.alerts.telegram.httpx.AsyncClient") as client:
            ok = await telegram.send_alert(_alert(), _settings())
        assert ok is False
        client.assert_not_called()

    async def test_posts_when_enabled(self) -> None:
        cfg = _settings(tg_token="123:abc", tg_chat="-100999")

        class _Resp:
            status_code = 200

            def raise_for_status(self) -> None:  # noqa: D401
                return None

            def json(self) -> dict[str, object]:
                return {"ok": True}

        post = AsyncMock(return_value=_Resp())
        client = AsyncMock()
        client.__aenter__.return_value.post = post
        with patch("wsb_crawler.alerts.telegram.httpx.AsyncClient", return_value=client):
            ok = await telegram.send_alert(_alert(), cfg)

        assert ok is True
        assert post.await_count == 1
        url, kwargs = post.await_args.args[0], post.await_args.kwargs
        assert "/bot123:abc/sendMessage" in url
        assert kwargs["json"]["chat_id"] == "-100999"
        assert kwargs["json"]["parse_mode"] == "HTML"


class TestDispatch:
    async def test_sends_to_both_channels(self) -> None:
        from wsb_crawler.alerts import dispatch

        cfg = _settings(tg_token="t", tg_chat="c")
        alerts = [_alert()]
        with (
            patch(
                "wsb_crawler.alerts.dispatch.discord.send_alert",
                new=AsyncMock(return_value=True),
            ) as d,
            patch(
                "wsb_crawler.alerts.dispatch.telegram.send_alert",
                new=AsyncMock(return_value=True),
            ) as t,
        ):
            count = await dispatch.send_alerts(alerts, cfg)

        assert count == 1
        assert alerts[0].sent is True
        d.assert_awaited_once()
        t.assert_awaited_once()

    async def test_telegram_skipped_when_disabled(self) -> None:
        from wsb_crawler.alerts import dispatch

        cfg = _settings()  # telegram disabled
        with (
            patch(
                "wsb_crawler.alerts.dispatch.discord.send_alert",
                new=AsyncMock(return_value=True),
            ),
            patch("wsb_crawler.alerts.dispatch.telegram.send_alert", new=AsyncMock()) as t,
        ):
            count = await dispatch.send_alerts([_alert()], cfg)

        assert count == 1
        t.assert_not_awaited()

    async def test_marks_sent_when_only_telegram_succeeds(self) -> None:
        from wsb_crawler.alerts import dispatch

        cfg = _settings(tg_token="t", tg_chat="c")
        alerts = [_alert()]
        with (
            patch(
                "wsb_crawler.alerts.dispatch.discord.send_alert",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "wsb_crawler.alerts.dispatch.telegram.send_alert",
                new=AsyncMock(return_value=True),
            ),
        ):
            count = await dispatch.send_alerts(alerts, cfg)

        assert count == 1
        assert alerts[0].sent is True
