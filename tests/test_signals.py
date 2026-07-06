"""Tests für Engagement- und Sentiment-Signale."""

from __future__ import annotations

from datetime import UTC, datetime

from wsb_crawler.analysis.signals import compute_signals, score_sentiment
from wsb_crawler.models import TickerMention


def _mention(ticker: str, *, score: int, context: str) -> TickerMention:
    return TickerMention(
        ticker=ticker,
        post_id="p1",
        subreddit="wallstreetbets",
        context=context,
        score=score,
        created_utc=datetime.now(tz=UTC),
    )


# ── score_sentiment ──────────────────────────────────────────────────────────


def test_bullish_keywords_counted() -> None:
    bull, bear = score_sentiment("loading up on GME calls, this thing is going to moon 🚀")
    assert bull >= 2
    assert bear == 0


def test_bearish_keywords_counted() -> None:
    bull, bear = score_sentiment("puts loaded, expecting a crash and a dump 📉")
    assert bear >= 2
    assert bull == 0


def test_word_boundaries_avoid_partial_matches() -> None:
    # "called" darf nicht als "call" zählen, "buyer" nicht als "buy"
    bull, bear = score_sentiment("he called the buyer yesterday")
    assert bull == 0
    assert bear == 0


def test_neutral_text_scores_zero() -> None:
    assert score_sentiment("the earnings report is due next week") == (0, 0)


# ── compute_signals ──────────────────────────────────────────────────────────


def test_aggregates_scores_and_sentiment() -> None:
    mentions = [
        _mention("GME", score=1000, context="GME calls to the moon 🚀"),
        _mention("GME", score=200, context="holding GME long"),
        _mention("AMC", score=5, context="AMC puts, this will dump"),
    ]
    signals = compute_signals(mentions)

    gme = signals["GME"]
    assert gme.mention_count == 2
    assert gme.total_score == 1200
    assert gme.max_score == 1000
    assert gme.avg_score == 600.0
    assert gme.sentiment > 0  # bullish
    assert gme.sentiment_label == "bullish"

    amc = signals["AMC"]
    assert amc.sentiment < 0  # bearish
    assert amc.sentiment_label == "bearish"


def test_engagement_weight_is_bounded_and_monotone() -> None:
    low = compute_signals([_mention("A", score=5, context="A")])["A"]
    high = compute_signals([_mention("B", score=5000, context="B")])["B"]
    assert 0.0 <= low.engagement_weight <= 1.0
    assert 0.0 <= high.engagement_weight <= 1.0
    assert high.engagement_weight > low.engagement_weight


def test_negative_scores_clamped_to_zero_engagement() -> None:
    sig = compute_signals([_mention("X", score=-50, context="X")])["X"]
    assert sig.engagement_weight == 0.0


def test_empty_mentions_yield_empty_signals() -> None:
    assert compute_signals([]) == {}
