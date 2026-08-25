"""Tests für die Direktlinks in Discord- und Telegram-Alerts."""

from __future__ import annotations

from datetime import UTC, datetime

from wsb_crawler.alerts.discord import _build_alert_embed
from wsb_crawler.alerts.links import (
    chart_url,
    community_url,
    link_targets,
    quote_url,
    reddit_search_url,
)
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
from wsb_crawler.models import Alert, AlertReason, SpikeResult


def _settings(subreddits: list[str] | None = None) -> Settings:
    return Settings(
        reddit=RedditSettings(client_id="a", client_secret="b", user_agent="c"),
        discord=DiscordSettings(webhook_url="https://discord.com/api/webhooks/1/x"),
        telegram=TelegramSettings(),
        newsapi=NewsAPISettings(key=""),
        alerts=AlertSettings(),
        crawler=CrawlerSettings(subreddits=subreddits or ["wallstreetbets"]),
    )


def _alert(ticker: str = "GME", isin: str | None = None) -> Alert:
    spike = SpikeResult(
        ticker=ticker,
        current_mentions=40,
        avg_mentions=10.0,
        ratio=4.0,
        delta=30,
        is_new=False,
        reason=AlertReason.SPIKE,
        confidence=70,
        isin=isin,
    )
    alert = Alert(ticker=ticker, reason=AlertReason.SPIKE, spike=spike)
    alert.triggered_at = datetime.now(tz=UTC)
    return alert


class TestLinkBuilders:
    def test_quote_url_points_at_yahoo(self) -> None:
        assert quote_url("GME") == "https://finance.yahoo.com/quote/GME"

    def test_ticker_is_normalised(self) -> None:
        assert quote_url(" gme ") == "https://finance.yahoo.com/quote/GME"

    def test_chart_and_community_urls(self) -> None:
        assert chart_url("GME") == "https://www.tradingview.com/symbols/GME/"
        assert community_url("GME") == "https://stocktwits.com/symbol/GME"

    def test_reddit_search_uses_the_watched_subreddits(self) -> None:
        url = reddit_search_url("GME", ["wallstreetbets", "stocks"])
        assert "/r/wallstreetbets+stocks/search/" in url
        assert "q=%24GME" in url  # sucht nach $GME
        assert "restrict_sr=1" in url

    def test_reddit_search_strips_the_r_prefix(self) -> None:
        assert "/r/stocks/search/" in reddit_search_url("GME", ["r/stocks"])

    def test_reddit_search_keeps_names_starting_with_r(self) -> None:
        # removeprefix statt lstrip — sonst würde "robinhood" zu "obinhood"
        assert "/r/robinhood/search/" in reddit_search_url("GME", ["robinhood"])

    def test_reddit_search_falls_back_without_subreddits(self) -> None:
        assert "/r/wallstreetbets/search/" in reddit_search_url("GME", [])

    def test_urls_are_escaped(self) -> None:
        # Kein rohes Sonderzeichen in der URL, egal was als Ticker ankommt
        assert quote_url("A B").endswith("A%20B")

    def test_link_targets_are_complete_and_ordered(self) -> None:
        labels = [label for label, _ in link_targets("GME", ["wallstreetbets"])]
        assert labels == ["Yahoo Finance", "Chart", "Stocktwits", "Reddit"]


class TestDiscordEmbedLinks:
    def test_title_links_to_the_quote_page(self) -> None:
        embed = _build_alert_embed(_alert(), _settings())
        assert embed["url"] == "https://finance.yahoo.com/quote/GME"

    def test_link_field_is_present(self) -> None:
        embed = _build_alert_embed(_alert(), _settings())
        field = next(f for f in embed["fields"] if f["name"] == "🔗 Nachschauen")
        assert "[Yahoo Finance](https://finance.yahoo.com/quote/GME)" in field["value"]
        assert "[Chart](https://www.tradingview.com/symbols/GME/)" in field["value"]
        assert "[Stocktwits](https://stocktwits.com/symbol/GME)" in field["value"]
        assert "[Reddit](https://www.reddit.com/r/wallstreetbets/search/" in field["value"]

    def test_link_field_follows_the_content_fields(self) -> None:
        # Die Links sind Zusatzinfo — sie sollen die Aussage nicht verdrängen
        embed = _build_alert_embed(_alert(), _settings())
        assert embed["fields"][-1]["name"] == "🔗 Nachschauen"

    def test_reddit_link_uses_configured_subreddits(self) -> None:
        embed = _build_alert_embed(_alert(), _settings(["wallstreetbets", "stocks"]))
        field = next(f for f in embed["fields"] if f["name"] == "🔗 Nachschauen")
        assert "/r/wallstreetbets+stocks/search/" in field["value"]


class TestIsinInAlerts:
    ISIN = "US36467W1099"

    def test_discord_shows_the_isin_as_code(self) -> None:
        embed = _build_alert_embed(_alert(isin=self.ISIN), _settings())
        field = next(f for f in embed["fields"] if "ISIN" in f["name"])
        # Codeblock, damit sich der Wert in Discord mit einem Klick kopieren lässt
        assert field["value"] == f"`{self.ISIN}`"

    def test_discord_omits_the_field_without_an_isin(self) -> None:
        embed = _build_alert_embed(_alert(), _settings())
        assert not [f for f in embed["fields"] if "ISIN" in f["name"]]

    def test_telegram_shows_the_isin(self) -> None:
        text = _build_message(_alert(isin=self.ISIN), ["wallstreetbets"])
        assert f"<code>{self.ISIN}</code>" in text

    def test_telegram_omits_the_isin_when_missing(self) -> None:
        assert "ISIN" not in _build_message(_alert(), ["wallstreetbets"])


class TestTelegramMessageLinks:
    def test_links_are_rendered_as_html_anchors(self) -> None:
        text = _build_message(_alert(), ["wallstreetbets"])
        assert '<a href="https://finance.yahoo.com/quote/GME">Yahoo Finance</a>' in text
        assert '<a href="https://stocktwits.com/symbol/GME">Stocktwits</a>' in text

    def test_link_line_is_last(self) -> None:
        text = _build_message(_alert(), ["wallstreetbets"])
        assert text.splitlines()[-1].startswith("🔗 ")

    def test_works_without_subreddits(self) -> None:
        text = _build_message(_alert())
        assert "/r/wallstreetbets/search/" in text
