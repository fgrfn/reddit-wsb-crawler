"""
Tests für die Discord-Embed-Erzeugung (alerts/discord.py).

Reine Formatierungs-/Embed-Funktionen — kein Netzwerk.
"""

from __future__ import annotations

from datetime import UTC, datetime

from wsb_crawler.__version__ import __version__
from wsb_crawler.alerts.discord import (
    _build_alert_embed,
    _build_heartbeat_embed,
    _format_change,
    _format_price,
)
from wsb_crawler.config import (
    AlertSettings,
    CrawlerSettings,
    DiscordSettings,
    NewsAPISettings,
    RedditSettings,
    Settings,
)
from wsb_crawler.models import (
    Alert,
    AlertReason,
    MarketStatus,
    PriceData,
    RunStatus,
    SpikeResult,
)


def _settings() -> Settings:
    return Settings(
        reddit=RedditSettings(client_id="a", client_secret="b"),
        newsapi=NewsAPISettings(key="k"),
        discord=DiscordSettings(webhook_url="https://discord.com/api/webhooks/1/x"),
        alerts=AlertSettings(),
        crawler=CrawlerSettings(subreddits=["wallstreetbets"]),
    )


class TestFormatting:
    def test_format_price_usd(self):
        assert _format_price(42.5, "USD") == "$42.50"

    def test_format_price_other_currency(self):
        assert _format_price(10.0, "EUR") == "EUR 10.00"

    def test_format_price_none(self):
        assert _format_price(None) == "—"

    def test_format_change_positive(self):
        assert _format_change(5.25) == "+5.25%"

    def test_format_change_negative(self):
        assert _format_change(-3.1) == "-3.10%"

    def test_format_change_none(self):
        assert _format_change(None) == "—"


class TestAlertEmbed:
    def test_alert_footer_uses_package_version(self):
        spike = SpikeResult(
            ticker="GME",
            current_mentions=25,
            avg_mentions=0.0,
            ratio=float("inf"),
            delta=25,
            is_new=True,
            reason=AlertReason.NEW_TICKER,
        )
        alert = Alert(ticker="GME", reason=AlertReason.NEW_TICKER, spike=spike)
        embed = _build_alert_embed(alert, _settings())

        assert embed["footer"]["text"].startswith(f"WSB-Crawler v{__version__}")
        assert "v2" not in embed["footer"]["text"]

    def test_new_ticker_embed(self):
        spike = SpikeResult(
            ticker="GME",
            current_mentions=25,
            avg_mentions=0.0,
            ratio=float("inf"),
            delta=25,
            is_new=True,
            reason=AlertReason.NEW_TICKER,
        )
        alert = Alert(ticker="GME", reason=AlertReason.NEW_TICKER, spike=spike)
        embed = _build_alert_embed(alert, _settings())
        assert "GME" in embed["title"]
        assert embed["fields"][0]["name"] == "Warum dieser Alert?"
        assert any(f["name"] == "📊 Erwähnungen" for f in embed["fields"])

    def test_spike_embed_with_price(self):
        price = PriceData(
            ticker="GME",
            company_name="GameStop Corp.",
            price=42.0,
            currency="USD",
            change_24h=8.5,
            change_1h=1.2,
            change_7d=-3.0,
            market_status=MarketStatus.OPEN,
        )
        spike = SpikeResult(
            ticker="GME",
            current_mentions=35,
            avg_mentions=10.0,
            ratio=3.5,
            delta=25,
            is_new=False,
            reason=AlertReason.SPIKE,
            price_data=price,
        )
        alert = Alert(ticker="GME", reason=AlertReason.SPIKE, spike=spike)
        embed = _build_alert_embed(alert, _settings())
        assert "GameStop Corp." in embed["title"]
        # Kurs-Feld vorhanden
        assert any(f["name"] == "💰 Kurs" for f in embed["fields"])

    def test_alert_embed_explains_reason_and_confidence(self):
        spike = SpikeResult(
            ticker="GME",
            current_mentions=35,
            avg_mentions=10.0,
            ratio=3.5,
            delta=25,
            is_new=False,
            confidence=82,
            reason=AlertReason.SPIKE,
        )
        alert = Alert(ticker="GME", reason=AlertReason.SPIKE, spike=spike)
        embed = _build_alert_embed(alert, _settings())

        reason = next(f for f in embed["fields"] if f["name"] == "Warum dieser Alert?")
        assert "Confidence 82/100" in reason["value"]
        assert "3.5x" in reason["value"]
        assert "+25" in reason["value"]


class TestHeartbeatEmbed:
    def test_heartbeat_footer_uses_package_version(self):
        status = RunStatus(
            last_run_at=None,
            last_run_duration_seconds=None,
            total_runs=0,
            total_alerts_sent=0,
            tracked_tickers=0,
            next_run_at=None,
            is_healthy=True,
        )
        embed = _build_heartbeat_embed(status)

        assert embed["footer"]["text"].startswith(f"WSB-Crawler v{__version__}")
        assert "v2" not in embed["footer"]["text"]

    def test_heartbeat_with_last_run(self):
        status = RunStatus(
            last_run_at=datetime.now(tz=UTC),
            last_run_duration_seconds=12.0,
            total_runs=5,
            total_alerts_sent=2,
            tracked_tickers=10,
            next_run_at=datetime.now(tz=UTC),
            is_healthy=True,
        )
        embed = _build_heartbeat_embed(status)
        assert embed["title"].startswith("💓")
        assert any("Nächster Lauf" in f["name"] for f in embed["fields"])

    def test_heartbeat_empty(self):
        status = RunStatus(
            last_run_at=None,
            last_run_duration_seconds=None,
            total_runs=0,
            total_alerts_sent=0,
            tracked_tickers=0,
            next_run_at=None,
            is_healthy=True,
        )
        embed = _build_heartbeat_embed(status)
        assert embed["fields"][0]["value"] == "—"
