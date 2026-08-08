"""Tests für den Entry-Point (main.py).

Schwerpunkt ist der Scheduler-Loop: Ein Fehler darin bedeutet, dass gar nicht
mehr gecrawlt wird — und zwar lautlos. Der Loop muss also jeden Einzelfehler
(Crawl, Heartbeat, Settings-Reload) überleben.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wsb_crawler import main
from wsb_crawler.config import (
    AlertSettings,
    CrawlerSettings,
    DiscordSettings,
    NewsAPISettings,
    RedditSettings,
    Settings,
)
from wsb_crawler.models import RunStatus


class _BreakLoop(Exception):
    """Bricht den Endlos-Loop im Test kontrolliert ab."""


def _settings(interval: int = 30) -> Settings:
    return Settings(
        reddit=RedditSettings("a", "b"),
        newsapi=NewsAPISettings(key=""),
        discord=DiscordSettings("https://discord.com/api/webhooks/1/x"),
        alerts=AlertSettings(),
        crawler=CrawlerSettings(crawl_interval_minutes=interval),
    )


def _run_status() -> RunStatus:
    return RunStatus(
        last_run_at=None,
        last_run_duration_seconds=None,
        total_runs=0,
        total_alerts_sent=0,
        tracked_tickers=0,
        next_run_at=None,
        is_healthy=True,
    )


def _sleep_breaking_after(count: int) -> AsyncMock:
    """asyncio.sleep-Ersatz, der nach `count` Aufrufen abbricht."""
    calls: list[float] = []

    async def _fake(seconds: float = 0) -> None:
        calls.append(seconds)
        if len(calls) >= count:
            raise _BreakLoop
        return None

    mock = AsyncMock(side_effect=_fake)
    mock.slept = calls  # type: ignore[attr-defined]
    return mock


class TestSchedulerLoop:
    async def _run(
        self,
        *,
        configured: list[bool],
        crawl: AsyncMock | None = None,
        settings: AsyncMock | None = None,
        heartbeat: AsyncMock | None = None,
        status: AsyncMock | None = None,
        break_after: int = 1,
    ) -> dict:
        db = MagicMock()
        db.get_run_status = status or AsyncMock(return_value=_run_status())
        sleep = _sleep_breaking_after(break_after)

        with (
            patch.object(main, "is_configured", new=AsyncMock(side_effect=configured)),
            patch.object(main, "get_settings", new=settings or AsyncMock(return_value=_settings())),
            patch.object(main, "run_single_crawl", new=crawl or AsyncMock()),
            patch.object(main, "send_heartbeat", new=heartbeat or AsyncMock()),
            patch.object(main.asyncio, "sleep", new=sleep),
            pytest.raises(_BreakLoop),
        ):
            await main.scheduler_loop(db)
        return {"slept": sleep.slept, "db": db}  # type: ignore[attr-defined]

    async def test_waits_until_configured_before_crawling(self) -> None:
        crawl = AsyncMock()
        # Erst zwei Mal unkonfiguriert, dann konfiguriert
        result = await self._run(configured=[False, False, True], crawl=crawl, break_after=3)
        # Zwei Wartezyklen à 5 s, danach beginnt der Crawl
        assert result["slept"][:2] == [5, 5]
        crawl.assert_awaited()

    async def test_runs_crawl_and_sleeps_until_next_run(self) -> None:
        crawl = AsyncMock()
        result = await self._run(configured=[True], crawl=crawl, break_after=1)
        crawl.assert_awaited_once()
        # Schlafdauer entspricht dem Intervall (30 Min.), etwas Toleranz für Laufzeit
        assert 29 * 60 <= result["slept"][0] <= 30 * 60

    async def test_failing_crawl_does_not_kill_the_loop(self) -> None:
        crawl = AsyncMock(side_effect=RuntimeError("Reddit weg"))
        heartbeat = AsyncMock()
        result = await self._run(configured=[True], crawl=crawl, heartbeat=heartbeat)
        # Trotz Crawl-Fehler wird weitergeplant und geschlafen
        assert result["slept"], "Loop hat nach Crawl-Fehler nicht weitergemacht"
        heartbeat.assert_awaited_once()

    async def test_failing_heartbeat_does_not_kill_the_loop(self) -> None:
        result = await self._run(
            configured=[True], heartbeat=AsyncMock(side_effect=RuntimeError("Discord weg"))
        )
        assert result["slept"], "Loop hat nach Heartbeat-Fehler nicht weitergemacht"

    async def test_failing_status_query_does_not_kill_the_loop(self) -> None:
        result = await self._run(
            configured=[True], status=AsyncMock(side_effect=RuntimeError("DB weg"))
        )
        assert result["slept"], "Loop hat nach Status-Fehler nicht weitergemacht"

    async def test_failing_settings_reload_keeps_previous_config(self) -> None:
        # Erster Aufruf liefert Settings, der Reload scheitert
        settings = AsyncMock(side_effect=[_settings(interval=30), RuntimeError("DB weg")])
        result = await self._run(configured=[True], settings=settings)
        # Alte Config bleibt gültig → weiter mit 30-Minuten-Intervall
        assert 29 * 60 <= result["slept"][0] <= 30 * 60

    async def test_heartbeat_receives_the_next_run_time(self) -> None:
        heartbeat = AsyncMock()
        with (
            patch.object(main, "is_configured", new=AsyncMock(return_value=True)),
            patch.object(main, "get_settings", new=AsyncMock(return_value=_settings())),
            patch.object(main, "run_single_crawl", new=AsyncMock()),
            patch.object(main, "send_heartbeat", new=heartbeat),
            patch.object(main.asyncio, "sleep", new=_sleep_breaking_after(1)),
            pytest.raises(_BreakLoop),
        ):
            db = MagicMock()
            db.get_run_status = AsyncMock(return_value=_run_status())
            await main.scheduler_loop(db)

        status = heartbeat.await_args.args[0]
        assert status.next_run_at is not None
        assert status.next_run_at > dt.datetime.now(tz=dt.UTC)


class TestBotSupervisor:
    async def _run(self, *, db_token: str, env: dict[str, str], break_after: int = 1) -> dict:
        db = MagicMock()
        db.get_setting = AsyncMock(return_value=db_token)
        start = AsyncMock()
        sleep = _sleep_breaking_after(break_after)

        with (
            patch.dict("os.environ", env, clear=False),
            patch.object(main.discord_bot, "set_database", new=MagicMock()),
            patch.object(main.discord_bot, "start_bot", new=start),
            patch.object(main.asyncio, "sleep", new=sleep),
            pytest.raises(_BreakLoop),
        ):
            await main.bot_supervisor(db)
        return {"start": start, "slept": sleep.slept}  # type: ignore[attr-defined]

    async def test_starts_bot_with_token_from_database(self) -> None:
        result = await self._run(db_token="db-token", env={"DISCORD_BOT_TOKEN": ""})
        result["start"].assert_awaited_once_with("db-token")

    async def test_env_token_wins_over_database(self) -> None:
        result = await self._run(db_token="db-token", env={"DISCORD_BOT_TOKEN": "env-token"})
        result["start"].assert_awaited_once_with("env-token")

    async def test_without_token_it_waits_instead_of_spinning(self) -> None:
        result = await self._run(db_token="", env={"DISCORD_BOT_TOKEN": ""})
        result["start"].assert_not_awaited()
        assert result["slept"] == [main.BOT_RETRY_SECONDS]

    async def test_bot_exit_leads_to_a_retry(self) -> None:
        # Bot kehrt zurück (Verbindungsabbruch) → Supervisor wartet und startet neu
        result = await self._run(db_token="tok", env={"DISCORD_BOT_TOKEN": ""}, break_after=2)
        assert result["start"].await_count >= 1
        assert result["slept"][0] == main.BOT_RETRY_SECONDS


class TestSigtermHandler:
    def test_handler_cancels_all_tasks(self) -> None:
        registered: dict = {}

        def _add_signal_handler(sig, callback):  # noqa: ANN001, ANN202
            registered["callback"] = callback

        loop = MagicMock()
        loop.add_signal_handler = _add_signal_handler
        tasks = [MagicMock(), MagicMock()]

        with patch.object(main.asyncio, "get_running_loop", return_value=loop):
            main._install_sigterm_handler(tasks)  # type: ignore[arg-type]

        registered["callback"]()
        for task in tasks:
            task.cancel.assert_called_once()

    def test_missing_signal_support_is_tolerated(self) -> None:
        # Windows kennt add_signal_handler nicht — darf nicht hochkommen
        loop = MagicMock()
        loop.add_signal_handler.side_effect = NotImplementedError
        with patch.object(main.asyncio, "get_running_loop", return_value=loop):
            main._install_sigterm_handler([])


class TestSetupLogging:
    def test_adds_sinks_without_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)  # Logdatei landet im tmp-Verzeichnis
        main._setup_logging("DEBUG")
        from loguru import logger

        logger.info("Testeintrag")
        assert (tmp_path / "logs" / "crawler.log").exists()


class TestMainAsync:
    async def test_injects_database_into_every_module(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fehlt eine Injektion, scheitert das betroffene Modul erst zur Laufzeit."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("WSB_NO_BROWSER", "1")

        injections = {
            name: MagicMock()
            for name in ("reddit_set_db", "discord_set_db", "news_set_db", "prices_set_db")
        }

        async def _noop(*args: object, **kwargs: object) -> None:
            return None

        with (
            patch.object(main, "DB_PATH", tmp_path / "test.db"),
            patch.object(main, "_setup_logging", new=MagicMock()),
            patch.object(main, "setup_ws_log_sink", new=MagicMock()),
            patch.object(main, "run_server", new=_noop),
            patch.object(main, "scheduler_loop", new=_noop),
            patch.object(main, "bot_supervisor", new=_noop),
            patch.object(main, "is_configured", new=AsyncMock(return_value=True)),
            patch.multiple(main, **injections),
        ):
            await main.main_async()

        for name, mock in injections.items():
            assert mock.call_count == 1, f"{name} wurde nicht aufgerufen"

    async def test_opens_browser_only_when_allowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("WSB_NO_BROWSER", "1")

        async def _noop(*args: object, **kwargs: object) -> None:
            return None

        with (
            patch.object(main, "DB_PATH", tmp_path / "b.db"),
            patch.object(main, "_setup_logging", new=MagicMock()),
            patch.object(main, "setup_ws_log_sink", new=MagicMock()),
            patch.object(main, "run_server", new=_noop),
            patch.object(main, "scheduler_loop", new=_noop),
            patch.object(main, "bot_supervisor", new=_noop),
            patch.object(main, "is_configured", new=AsyncMock(return_value=True)),
            patch.object(main.webbrowser, "open", new=MagicMock()) as browser,
        ):
            await main.main_async()
        browser.assert_not_called()  # WSB_NO_BROWSER=1


class TestMain:
    def test_keyboard_interrupt_exits_quietly(self) -> None:
        def _interrupt(coro: object) -> None:
            coro.close()  # type: ignore[attr-defined]  # sonst "never awaited"-Warnung
            raise KeyboardInterrupt

        with patch.object(main.asyncio, "run", side_effect=_interrupt):
            main.main()  # darf nicht durchschlagen

    def test_delegates_to_main_async(self) -> None:
        with patch.object(main.asyncio, "run") as run:
            main.main()
        run.assert_called_once()
        # Coroutine schließen, damit kein "never awaited"-Warning entsteht
        coro = run.call_args.args[0]
        assert asyncio.iscoroutine(coro)
        coro.close()
