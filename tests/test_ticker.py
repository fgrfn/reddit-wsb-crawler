"""
Tests für die Ticker-Erkennung (crawler/ticker.py).

Kein Netzwerk, keine DB — reine Unit-Tests.
"""

from datetime import datetime, timezone

import pytest

from wsb_crawler.crawler.ticker import (
    BLACKLIST,
    aggregate_mentions,
    extract_tickers,
)
from wsb_crawler.models import RedditPost


def _make_post(title: str = "", text: str = "", score: int = 100) -> RedditPost:
    return RedditPost(
        id="test123",
        subreddit="wallstreetbets",
        title=title,
        text=text,
        author="testuser",
        score=score,
        upvote_ratio=0.95,
        created_utc=datetime.now(tz=timezone.utc),
        url="https://reddit.com/r/wallstreetbets/test",
    )


class TestTickerExtraction:
    def test_explicit_dollar_ticker(self):
        """$GME wird immer erkannt."""
        post = _make_post(text="Ich kaufe $GME weil Tendies")
        mentions = extract_tickers(post)
        tickers = [m.ticker for m in mentions]
        assert "GME" in tickers

    def test_multiple_tickers(self):
        """Mehrere Ticker in einem Text."""
        post = _make_post(text="$GME und $AMC gehen bald to the moon 🚀")
        tickers = [m.ticker for m in extract_tickers(post)]
        assert "GME" in tickers
        assert "AMC" in tickers

    def test_title_and_text_combined(self):
        """Ticker aus Titel UND Text werden erkannt."""
        post = _make_post(title="$TSLA kurz vor Breakout", text="Chart sieht bullish aus")
        tickers = [m.ticker for m in extract_tickers(post)]
        assert "TSLA" in tickers

    def test_blacklist_filters_common_words(self):
        """Bekannte Abkürzungen werden herausgefiltert."""
        post = _make_post(text="THE FED raised rates AND the market went DOWN")
        tickers = [m.ticker for m in extract_tickers(post)]
        assert "THE" not in tickers
        assert "AND" not in tickers
        assert "FED" not in tickers
        assert "DOWN" not in tickers

    def test_dedup_within_post(self):
        """Derselbe Ticker wird pro Post nur einmal gezählt."""
        post = _make_post(text="$GME $GME $GME GME GME GME to the moon")
        mentions = extract_tickers(post)
        gme_mentions = [m for m in mentions if m.ticker == "GME"]
        assert len(gme_mentions) == 1

    def test_context_captured(self):
        """Kontext rund um den Ticker wird gespeichert."""
        post = _make_post(text="Ich denke $GME ist undervalued und kaufe mehr")
        mentions = extract_tickers(post)
        gme = next(m for m in mentions if m.ticker == "GME")
        assert "GME" in gme.context
        assert len(gme.context) > 0

    def test_short_single_char_filtered(self):
        """Einzelne Buchstaben werden nicht als Ticker erkannt."""
        post = _make_post(text="I am going to buy A lot of stocks")
        tickers = [m.ticker for m in extract_tickers(post)]
        assert "I" not in tickers
        assert "A" not in tickers

    def test_empty_post(self):
        """Leerer Post gibt keine Mentions zurück."""
        post = _make_post(title="", text="")
        assert extract_tickers(post) == []

    def test_numeric_strings_filtered(self):
        """Rein numerische Strings werden nicht als Ticker gewertet."""
        post = _make_post(text="Stock went up 200 percent today, 300 is next target")
        tickers = [m.ticker for m in extract_tickers(post)]
        assert "200" not in tickers
        assert "300" not in tickers

    def test_wsb_slang_filtered(self):
        """WSB-typische Abkürzungen sind auf der Blacklist."""
        post = _make_post(text="YOLO DD on PUTS, going ITM ATM OTM HODL")
        tickers = [m.ticker for m in extract_tickers(post)]
        for word in ["YOLO", "DD", "ITM", "ATM", "OTM", "HODL"]:
            assert word not in tickers


class TestAggregation:
    def test_aggregate_counts_correctly(self):
        """Mehrere Mentions werden korrekt summiert."""
        now = datetime.now(tz=timezone.utc)

        def _mention(ticker: str, post_id: str):
            from wsb_crawler.models import TickerMention
            return TickerMention(
                ticker=ticker,
                post_id=post_id,
                subreddit="wallstreetbets",
                context="...",
                score=100,
                created_utc=now,
            )

        mentions = [
            _mention("GME", "post1"),
            _mention("GME", "post2"),
            _mention("GME", "post3"),
            _mention("AMC", "post1"),
            _mention("AMC", "post2"),
            _mention("TSLA", "post1"),
        ]

        counts = aggregate_mentions(mentions)
        assert counts["GME"] == 3
        assert counts["AMC"] == 2
        assert counts["TSLA"] == 1

    def test_aggregate_sorted_by_count(self):
        """Ergebnis ist nach Häufigkeit sortiert (häufigste zuerst)."""
        from wsb_crawler.models import TickerMention
        now = datetime.now(tz=timezone.utc)

        mentions = [
            TickerMention("TSLA", "p1", "wsb", "...", 100, now),
            TickerMention("GME", "p1", "wsb", "...", 100, now),
            TickerMention("GME", "p2", "wsb", "...", 100, now),
            TickerMention("GME", "p3", "wsb", "...", 100, now),
        ]

        counts = aggregate_mentions(mentions)
        keys = list(counts.keys())
        assert keys[0] == "GME"   # häufigste zuerst
        assert keys[1] == "TSLA"

    def test_aggregate_empty(self):
        """Leere Liste → leeres Dict."""
        assert aggregate_mentions([]) == {}


class TestBlacklist:
    def test_blacklist_is_frozenset(self):
        """Blacklist ist ein frozenset für O(1) Lookup."""
        assert isinstance(BLACKLIST, frozenset)

    def test_common_finance_terms_blacklisted(self):
        """Wichtige Finance-Begriffe sind in der Blacklist."""
        for term in ["ETF", "IPO", "SEC", "CEO", "FED", "YOLO", "HODL", "DD"]:
            assert term in BLACKLIST, f"{term} sollte in der Blacklist sein"

    def test_valid_tickers_not_blacklisted(self):
        """Bekannte Ticker sind NICHT in der Blacklist."""
        for ticker in ["GME", "AMC", "TSLA", "NVDA", "AAPL"]:
            assert ticker not in BLACKLIST, f"{ticker} sollte nicht in der Blacklist sein"
