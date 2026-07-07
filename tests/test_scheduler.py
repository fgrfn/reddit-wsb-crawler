"""Tests für die Scheduler-Zeitplanung (_next_run_at in main.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from wsb_crawler.config import (
    AlertSettings,
    CrawlerSettings,
    DiscordSettings,
    NewsAPISettings,
    RedditSettings,
    Settings,
)
from wsb_crawler.main import _next_run_at


def _settings(**crawler_kwargs: object) -> Settings:
    return Settings(
        reddit=RedditSettings("i", "s", "ua"),
        newsapi=NewsAPISettings(key=""),
        discord=DiscordSettings("https://discord.com/api/webhooks/1/x"),
        alerts=AlertSettings(),
        crawler=CrawlerSettings(**crawler_kwargs),  # type: ignore[arg-type]
    )


_NOW = datetime(2026, 7, 6, 14, 24, tzinfo=UTC)


def test_interval_mode_adds_minutes() -> None:
    cfg = _settings(schedule_mode="interval", crawl_interval_minutes=30)
    assert _next_run_at(cfg, _NOW) == _NOW + timedelta(minutes=30)


def test_cron_mode_uses_cron() -> None:
    cfg = _settings(schedule_mode="cron", cron_expression="0 */2 * * *")
    assert _next_run_at(cfg, _NOW) == datetime(2026, 7, 6, 16, 0, tzinfo=UTC)


def test_cron_mode_empty_expression_falls_back_to_interval() -> None:
    cfg = _settings(schedule_mode="cron", cron_expression="", crawl_interval_minutes=15)
    assert _next_run_at(cfg, _NOW) == _NOW + timedelta(minutes=15)


def test_invalid_cron_falls_back_to_interval() -> None:
    cfg = _settings(schedule_mode="cron", cron_expression="not a cron", crawl_interval_minutes=45)
    assert _next_run_at(cfg, _NOW) == _NOW + timedelta(minutes=45)
