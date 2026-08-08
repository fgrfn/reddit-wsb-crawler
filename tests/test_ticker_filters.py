"""Tests für die konfigurierbaren Ticker-Filter (eigene Blacklist + Ausnahmen)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wsb_crawler.config import get_settings
from wsb_crawler.crawler.ticker import BLACKLIST, effective_blacklist, extract_tickers
from wsb_crawler.models import RedditPost
from wsb_crawler.storage.database import Database


def _post(text: str) -> RedditPost:
    return RedditPost(
        id="p1",
        subreddit="wsb",
        title="",
        text=text,
        author="u",
        score=10,
        upvote_ratio=0.9,
        created_utc=datetime.now(tz=UTC),
        url="https://reddit.com/x",
        is_comment=False,
    )


class TestEffectiveBlacklist:
    def test_defaults_to_the_builtin_list(self) -> None:
        assert effective_blacklist() == BLACKLIST

    def test_extra_entries_are_added(self) -> None:
        blocked = effective_blacklist(extra=["yolo2", "pump"])
        assert "YOLO2" in blocked
        assert "PUMP" in blocked

    def test_entries_are_normalised(self) -> None:
        blocked = effective_blacklist(extra=[" $pump ", "dump"])
        assert "PUMP" in blocked  # $ und Leerzeichen entfernt, großgeschrieben
        assert "DUMP" in blocked

    def test_allowlist_lifts_builtin_entries(self) -> None:
        assert "WEN" in BLACKLIST
        blocked = effective_blacklist(allowlist=["WEN"])
        assert "WEN" not in blocked
        assert "LMAO" in blocked  # Rest der Standardliste bleibt

    def test_allowlist_wins_over_extra(self) -> None:
        # Widersprüchliche Angabe: die Ausnahme gewinnt, sonst wäre ein bewusst
        # erlaubter Ticker doch blockiert
        blocked = effective_blacklist(extra=["GME"], allowlist=["GME"])
        assert "GME" not in blocked

    def test_empty_entries_are_ignored(self) -> None:
        assert effective_blacklist(extra=["", "   "], allowlist=["", " "]) == BLACKLIST


class TestExtractionWithFilters:
    def test_own_entry_blocks_both_notations(self) -> None:
        blocked = effective_blacklist(extra=["PUMP"])
        # Auch die $-Schreibweise wird geblockt — sonst wäre der Filter wirkungslos
        assert extract_tickers(_post("$PUMP jetzt"), blacklist=blocked) == []
        assert extract_tickers(_post("PUMP incoming"), blacklist=blocked) == []

    def test_allowlisted_ticker_is_found_again(self) -> None:
        # Ohne Ausnahme wird WEN gefiltert …
        assert extract_tickers(_post("$WEN to the moon")) == []
        # … mit Ausnahme nicht mehr
        blocked = effective_blacklist(allowlist=["WEN"])
        found = [m.ticker for m in extract_tickers(_post("$WEN to the moon"), blacklist=blocked)]
        assert found == ["WEN"]

    def test_unrelated_tickers_are_unaffected(self) -> None:
        blocked = effective_blacklist(extra=["PUMP"])
        found = [m.ticker for m in extract_tickers(_post("$GME und $PUMP"), blacklist=blocked)]
        assert found == ["GME"]

    def test_default_behaviour_without_filters(self) -> None:
        found = [m.ticker for m in extract_tickers(_post("$GME calls"))]
        assert found == ["GME"]


class TestConfigParsing:
    @pytest.fixture
    async def db(self, tmp_path: Path) -> Database:
        database = Database(tmp_path / "f.db")
        await database.init()
        for key, value in (
            ("reddit_client_id", "x"),
            ("reddit_client_secret", "y"),
            ("discord_webhook_url", "https://discord.com/api/webhooks/1/z"),
        ):
            await database.set_setting(key, value)
        yield database
        await database.close()

    async def test_empty_by_default(self, db: Database) -> None:
        crawler = (await get_settings(db)).crawler
        assert crawler.ticker_blacklist_extra == []
        assert crawler.ticker_allowlist == []

    async def test_parses_and_normalises_lists(self, db: Database) -> None:
        await db.set_setting("ticker_blacklist_extra", " pump , $dump,, PUMP ")
        await db.set_setting("ticker_allowlist", "wen")
        crawler = (await get_settings(db)).crawler
        # Großschreibung, $ entfernt, Duplikate und Leereinträge weg
        assert crawler.ticker_blacklist_extra == ["PUMP", "DUMP"]
        assert crawler.ticker_allowlist == ["WEN"]

    async def test_newlines_work_as_separators(self, db: Database) -> None:
        await db.set_setting("ticker_blacklist_extra", "pump\ndump")
        crawler = (await get_settings(db)).crawler
        assert crawler.ticker_blacklist_extra == ["PUMP", "DUMP"]

    async def test_config_feeds_the_effective_blacklist(self, db: Database) -> None:
        """Der Weg von der Einstellung bis zur Erkennung."""
        await db.set_setting("ticker_blacklist_extra", "pump")
        await db.set_setting("ticker_allowlist", "wen")
        crawler = (await get_settings(db)).crawler

        blocked = effective_blacklist(
            extra=crawler.ticker_blacklist_extra, allowlist=crawler.ticker_allowlist
        )
        found = [m.ticker for m in extract_tickers(_post("$PUMP und $WEN"), blacklist=blocked)]
        assert found == ["WEN"]  # eigener Filter greift, Ausnahme greift
