"""Tests für den Discord-Bot (alerts/bot.py) inkl. Slash-Commands.

Die Commands sind Closures in `_register_commands`; getestet werden sie über
`bot.tree` und einen Interaction-Doppelgänger — inklusive der Fehlerpfade, die
im Betrieb sonst nur als „❌ Fehler" beim Nutzer sichtbar würden.
"""

from __future__ import annotations

import datetime as dt
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wsb_crawler.alerts import bot as botmod
from wsb_crawler.alerts.bot import _build_ascii_chart, get_bot
from wsb_crawler.models import RunStatus, TickerHistory, TrendDirection, TrendEntry


@pytest.fixture(autouse=True)
def _reset_db() -> Any:
    """Modul-globale DB-Injektion nach jedem Test zurücksetzen."""
    original = botmod._db
    yield
    botmod._db = original


class _Interaction:
    """Minimaler Interaction-Ersatz: merkt sich, was der Command gesendet hat."""

    def __init__(self) -> None:
        self.response = MagicMock()
        self.response.defer = AsyncMock()
        self.followup = MagicMock()
        self.followup.send = AsyncMock()

    @property
    def sent_text(self) -> str:
        args = self.followup.send.await_args
        if args is None:
            return ""
        return str(args.args[0]) if args.args else ""

    @property
    def sent_embed(self) -> Any:
        args = self.followup.send.await_args
        return args.kwargs.get("embed") if args else None


def _command(name: str) -> Any:
    """Holt den Callback eines registrierten Slash-Commands."""
    bot = get_bot()
    command = next(c for c in bot.tree.get_commands() if c.name == name)
    return command.callback


class TestAsciiChart:
    def test_empty_values(self) -> None:
        assert _build_ascii_chart([], []) == "Keine Daten"

    def test_all_zero_values(self) -> None:
        assert _build_ascii_chart([0, 0], ["a", "b"]) == "Keine Daten"

    def test_bars_scale_to_the_maximum(self) -> None:
        chart = _build_ascii_chart([5, 10], ["01.08", "02.08"], width=10)
        lines = chart.split("\n")[2:]  # Header + Trennlinie überspringen
        assert lines[0].count("█") == 5  # halber Balken
        assert lines[1].count("█") == 10  # voller Balken

    def test_labels_are_truncated_to_five_chars(self) -> None:
        chart = _build_ascii_chart([1], ["viel-zu-lang"], width=4)
        assert "viel-" in chart
        assert "viel-zu-lang" not in chart

    def test_values_are_appended(self) -> None:
        assert "42" in _build_ascii_chart([42], ["01.08"], width=5)


class TestDatabaseInjection:
    def test_get_db_without_injection_raises(self) -> None:
        botmod._db = None
        with pytest.raises(RuntimeError, match="nicht initialisiert"):
            botmod._get_db()

    def test_set_database_makes_it_available(self) -> None:
        db = MagicMock()
        botmod.set_database(db)
        assert botmod._get_db() is db


class TestGetBot:
    def test_registers_all_three_commands(self) -> None:
        names = {c.name for c in get_bot().tree.get_commands()}
        assert names == {"top", "chart", "status"}

    def test_returns_a_fresh_instance_each_time(self) -> None:
        # Kein Singleton: ein geschlossener Client lässt sich nicht neu starten
        assert get_bot() is not get_bot()


class TestTopCommand:
    async def test_posts_top_tickers(self) -> None:
        botmod.set_database(MagicMock())
        entries = [
            TrendEntry(
                ticker="GME",
                company_name="GameStop",
                total_mentions=100,
                avg_daily_mentions=14.3,
                peak_day=datetime.now(tz=UTC),
                peak_mentions=40,
                trend_direction=TrendDirection.UP,
            )
        ]
        interaction = _Interaction()
        with (
            patch.object(botmod, "get_top_tickers", new=AsyncMock(return_value=entries)) as top,
            patch.object(botmod, "send_top_tickers", new=AsyncMock()) as send,
        ):
            await _command("top")(interaction, days=14)

        interaction.response.defer.assert_awaited_once()
        assert top.await_args.kwargs["days"] == 14
        send.assert_awaited_once()
        assert "14 Tage" in interaction.sent_text

    async def test_error_is_reported_to_the_user(self) -> None:
        botmod.set_database(MagicMock())
        interaction = _Interaction()
        with patch.object(botmod, "get_top_tickers", new=AsyncMock(side_effect=RuntimeError("DB"))):
            await _command("top")(interaction)
        assert "❌" in interaction.sent_text


class TestChartCommand:
    @staticmethod
    def _history(points: int = 3) -> TickerHistory:
        base = datetime(2026, 8, 1, tzinfo=UTC)
        return TickerHistory(
            ticker="GME",
            mention_counts=[(base + dt.timedelta(days=i), (i + 1) * 5) for i in range(points)],
        )

    async def test_renders_chart_embed(self) -> None:
        botmod.set_database(MagicMock())
        interaction = _Interaction()
        with patch.object(
            botmod, "get_ticker_chart_data", new=AsyncMock(return_value=self._history())
        ):
            await _command("chart")(interaction, ticker="gme", days=30)

        embed = interaction.sent_embed
        assert embed is not None
        assert "$GME" in embed.title  # Ticker wird normalisiert (klein → groß)
        fields = {f.name: f.value for f in embed.fields}
        assert fields["Gesamt"] == "30"  # 5 + 10 + 15
        assert fields["Peak"] == "15"

    async def test_normalises_dollar_prefix(self) -> None:
        botmod.set_database(MagicMock())
        interaction = _Interaction()
        with patch.object(
            botmod, "get_ticker_chart_data", new=AsyncMock(return_value=self._history())
        ) as fetch:
            await _command("chart")(interaction, ticker="$gme")
        assert fetch.await_args.args[1] == "GME"

    async def test_without_data_it_says_so(self) -> None:
        botmod.set_database(MagicMock())
        interaction = _Interaction()
        empty = TickerHistory(ticker="XYZ", mention_counts=[])
        with patch.object(botmod, "get_ticker_chart_data", new=AsyncMock(return_value=empty)):
            await _command("chart")(interaction, ticker="XYZ", days=7)
        assert "Keine Daten" in interaction.sent_text
        assert interaction.sent_embed is None

    async def test_limits_to_twenty_data_points(self) -> None:
        botmod.set_database(MagicMock())
        interaction = _Interaction()
        with patch.object(
            botmod, "get_ticker_chart_data", new=AsyncMock(return_value=self._history(points=30))
        ):
            await _command("chart")(interaction, ticker="GME")
        # Nur die letzten 20 Punkte gehen in den Chart
        chart_lines = interaction.sent_embed.description.count("\n")
        assert chart_lines <= 24  # 20 Balken + Rahmen/Header

    async def test_error_is_reported_to_the_user(self) -> None:
        botmod.set_database(MagicMock())
        interaction = _Interaction()
        with patch.object(
            botmod, "get_ticker_chart_data", new=AsyncMock(side_effect=RuntimeError("kaputt"))
        ):
            await _command("chart")(interaction, ticker="GME")
        assert "❌" in interaction.sent_text


class TestStatusCommand:
    @staticmethod
    def _status(*, healthy: bool = True, with_run: bool = True) -> RunStatus:
        return RunStatus(
            last_run_at=datetime.now(tz=UTC) if with_run else None,
            last_run_duration_seconds=42.0 if with_run else None,
            total_runs=5,
            total_alerts_sent=3,
            tracked_tickers=120,
            next_run_at=None,
            is_healthy=healthy,
        )

    async def _run(self, status: RunStatus) -> _Interaction:
        from wsb_crawler.config import (
            AlertSettings,
            CrawlerSettings,
            DiscordSettings,
            NewsAPISettings,
            RedditSettings,
            Settings,
        )

        db = MagicMock()
        db.get_run_status = AsyncMock(return_value=status)
        botmod.set_database(db)
        cfg = Settings(
            reddit=RedditSettings("a", "b"),
            newsapi=NewsAPISettings(key=""),
            discord=DiscordSettings("https://discord.com/api/webhooks/1/x"),
            alerts=AlertSettings(),
            crawler=CrawlerSettings(crawl_interval_minutes=30),
        )
        interaction = _Interaction()
        with patch.object(botmod, "get_settings", new=AsyncMock(return_value=cfg)):
            await _command("status")(interaction)
        return interaction

    async def test_reports_healthy_status(self) -> None:
        interaction = await self._run(self._status())
        fields = {f.name: f.value for f in interaction.sent_embed.fields}
        assert fields["Status"] == "🟢 Gesund"
        assert fields["Dauer"] == "42s"
        assert fields["Alerts gesamt"] == "3"
        assert fields["Nächster Lauf"] != "—"  # aus letztem Lauf + Intervall

    async def test_reports_unhealthy_status(self) -> None:
        interaction = await self._run(self._status(healthy=False))
        fields = {f.name: f.value for f in interaction.sent_embed.fields}
        assert fields["Status"] == "🔴 Fehler"

    async def test_without_previous_run_shows_placeholders(self) -> None:
        interaction = await self._run(self._status(with_run=False))
        fields = {f.name: f.value for f in interaction.sent_embed.fields}
        assert fields["Letzter Lauf"] == "—"
        assert fields["Nächster Lauf"] == "—"
        assert fields["Dauer"] == "—"

    async def test_error_is_reported_to_the_user(self) -> None:
        db = MagicMock()
        db.get_run_status = AsyncMock(side_effect=RuntimeError("DB weg"))
        botmod.set_database(db)
        interaction = _Interaction()
        await _command("status")(interaction)
        assert "❌" in interaction.sent_text


class TestStartBot:
    async def test_starts_with_the_given_token(self) -> None:
        bot = MagicMock()
        bot.start = AsyncMock()
        bot.is_closed = MagicMock(return_value=False)
        bot.close = AsyncMock()
        with patch.object(botmod, "get_bot", return_value=bot):
            await botmod.start_bot("token-123")
        bot.start.assert_awaited_once_with("token-123")
        bot.close.assert_awaited_once()  # sauber schließen

    async def test_start_failure_is_swallowed_and_closed(self) -> None:
        bot = MagicMock()
        bot.start = AsyncMock(side_effect=RuntimeError("ungültiger Token"))
        bot.is_closed = MagicMock(return_value=False)
        bot.close = AsyncMock()
        with patch.object(botmod, "get_bot", return_value=bot):
            await botmod.start_bot("bad")  # darf nicht hochkommen
        bot.close.assert_awaited_once()

    async def test_already_closed_bot_is_not_closed_twice(self) -> None:
        bot = MagicMock()
        bot.start = AsyncMock()
        bot.is_closed = MagicMock(return_value=True)
        bot.close = AsyncMock()
        with patch.object(botmod, "get_bot", return_value=bot):
            await botmod.start_bot("tok")
        bot.close.assert_not_awaited()
