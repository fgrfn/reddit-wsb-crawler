"""Tests für das Multi-Listing-Crawling (hot/new/rising/top) inkl. Dedupe."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from wsb_crawler.config import VALID_LISTINGS
from wsb_crawler.crawler.reddit import _fetch_posts, _listing_iterator, _split_budget


class _FakeComments:
    def __init__(self, bodies: list[str]) -> None:
        self._bodies = bodies

    async def replace_more(self, limit: int = 0) -> None:
        return None

    def __iter__(self) -> Any:
        for i, body in enumerate(self._bodies):
            yield _FakeComment(f"c{i}", body)


class _FakeComment:
    def __init__(self, cid: str, body: str) -> None:
        self.id = cid
        self.body = body
        self.author = "commenter"
        self.score = 5
        self.created_utc = datetime(2026, 8, 6, tzinfo=UTC).timestamp()


class _FakeSubmission:
    def __init__(self, sid: str, *, comments: list[str] | None = None) -> None:
        self.id = sid
        self.title = f"Title {sid}"
        self.selftext = f"Body {sid} mentions $GME"
        self.author = "poster"
        self.score = 100
        self.upvote_ratio = 0.9
        self.created_utc = datetime(2026, 8, 6, tzinfo=UTC).timestamp()
        self.permalink = f"/r/test/comments/{sid}/"
        self.comment_sort = "best"
        self.comments = _FakeComments(comments or [])

    async def load(self) -> None:
        return None


class _FakeSubreddit:
    """Fake-Subreddit, der pro Listing definierte Submissions liefert."""

    def __init__(self, listings: dict[str, list[_FakeSubmission]]) -> None:
        self._listings = listings
        self.calls: list[tuple[str, int]] = []

    def _gen(self, name: str, limit: int) -> Any:
        self.calls.append((name, limit))
        items = self._listings.get(name, [])[:limit]

        async def _iter() -> Any:
            for item in items:
                yield item

        return _iter()

    def hot(self, limit: int = 0) -> Any:
        return self._gen("hot", limit)

    def new(self, limit: int = 0) -> Any:
        return self._gen("new", limit)

    def rising(self, limit: int = 0) -> Any:
        return self._gen("rising", limit)

    def top(self, limit: int = 0, time_filter: str = "day") -> Any:
        return self._gen("top", limit)


class _FakeReddit:
    def __init__(self, subreddit: _FakeSubreddit) -> None:
        self._subreddit = subreddit

    async def subreddit(self, name: str) -> _FakeSubreddit:
        return self._subreddit


class TestSplitBudget:
    def test_single_listing_gets_full_budget(self) -> None:
        assert _split_budget(100, 1) == 100

    def test_budget_split_evenly(self) -> None:
        assert _split_budget(90, 3) == 30
        assert _split_budget(100, 4) == 25

    def test_never_below_one(self) -> None:
        assert _split_budget(2, 3) == 1
        assert _split_budget(0, 3) == 1


class TestListingIterator:
    @pytest.mark.parametrize("listing", VALID_LISTINGS)
    def test_dispatches_each_listing(self, listing: str) -> None:
        sub = _FakeSubreddit({})
        _listing_iterator(sub, listing, 7)
        assert sub.calls == [(listing, 7)]

    def test_unknown_listing_falls_back_to_hot(self) -> None:
        sub = _FakeSubreddit({})
        _listing_iterator(sub, "bogus", 5)
        assert sub.calls == [("hot", 5)]


class TestFetchPosts:
    async def test_reads_all_configured_listings(self) -> None:
        sub = _FakeSubreddit(
            {
                "hot": [_FakeSubmission("h1")],
                "new": [_FakeSubmission("n1")],
                "rising": [_FakeSubmission("r1")],
            }
        )
        posts, _ = await _fetch_posts(
            _FakeReddit(sub),  # type: ignore[arg-type]
            "test",
            limit=30,
            comments_limit=0,
            listings=("hot", "new", "rising"),
        )
        assert [p.id for p in posts] == ["h1", "n1", "r1"]
        # Budget gleichmäßig verteilt → je 10
        assert sub.calls == [("hot", 10), ("new", 10), ("rising", 10)]

    async def test_deduplicates_posts_across_listings(self) -> None:
        shared = "dup1"
        sub = _FakeSubreddit(
            {
                "hot": [_FakeSubmission(shared), _FakeSubmission("h2")],
                "rising": [_FakeSubmission(shared), _FakeSubmission("r2")],
            }
        )
        posts, _ = await _fetch_posts(
            _FakeReddit(sub),  # type: ignore[arg-type]
            "test",
            limit=20,
            comments_limit=0,
            listings=("hot", "rising"),
        )
        ids = [p.id for p in posts]
        assert ids == [shared, "h2", "r2"]
        assert ids.count(shared) == 1

    async def test_default_is_hot_only(self) -> None:
        sub = _FakeSubreddit({"hot": [_FakeSubmission("h1")]})
        await _fetch_posts(
            _FakeReddit(sub),  # type: ignore[arg-type]
            "test",
            limit=50,
            comments_limit=0,
        )
        assert sub.calls == [("hot", 50)]

    async def test_collects_comments_per_post(self) -> None:
        sub = _FakeSubreddit(
            {
                "hot": [_FakeSubmission("h1", comments=["$AMC to the moon", "second"])],
                "new": [_FakeSubmission("n1", comments=["third"])],
            }
        )
        posts, comments = await _fetch_posts(
            _FakeReddit(sub),  # type: ignore[arg-type]
            "test",
            limit=20,
            comments_limit=5,
            listings=("hot", "new"),
        )
        assert len(posts) == 2
        assert [c.text for c in comments] == ["$AMC to the moon", "second", "third"]
        assert all(c.is_comment for c in comments)

    async def test_comments_respect_limit(self) -> None:
        sub = _FakeSubreddit({"hot": [_FakeSubmission("h1", comments=["a", "b", "c", "d"])]})
        _, comments = await _fetch_posts(
            _FakeReddit(sub),  # type: ignore[arg-type]
            "test",
            limit=10,
            comments_limit=2,
            listings=("hot",),
        )
        assert [c.text for c in comments] == ["a", "b"]
