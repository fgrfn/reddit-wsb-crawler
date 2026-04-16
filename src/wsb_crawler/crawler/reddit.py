"""
Async Reddit-Crawling via asyncpraw.

asyncpraw ist der offizielle async-Port von praw. Alle Netzwerk-Calls
sind awaitable, was paralleles Crawlen mehrerer Subreddits ermöglicht.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import asyncpraw
import asyncprawcore
from loguru import logger

from wsb_crawler.config import get_settings
from wsb_crawler.crawler.ticker import aggregate_mentions, extract_tickers
from wsb_crawler.models import CrawlResult, RedditPost, TickerMention

if TYPE_CHECKING:
    from wsb_crawler.storage.database import Database

_db: "Database | None" = None


def set_database(db: "Database") -> None:
    global _db
    _db = db


def _sanitize_credential(value: str, name: str) -> str:
    """Bereinigt einen Credential-String.

    - Entfernt führende/nachfolgende Whitespace-Zeichen (häufigste Fehlerquelle
      bei Copy-Paste aus Reddit/Discord-Dashboards).
    - Warnt explizit wenn Nicht-ASCII-Zeichen enthalten sind (aiohttp-Header
      akzeptieren nur ASCII), anstatt diese lautlos zu verwerfen.
    """
    stripped = value.strip()
    try:
        stripped.encode("ascii")
    except UnicodeEncodeError:
        logger.warning(
            "Credential '{}' enthält Nicht-ASCII-Zeichen — diese werden entfernt. "
            "Bitte Wert im Dashboard neu eingeben.",
            name,
        )
        stripped = stripped.encode("ascii", "ignore").decode("ascii")
    return stripped


def _make_reddit_client(cfg) -> asyncpraw.Reddit:
    kwargs: dict = {
        "client_id": _sanitize_credential(cfg.client_id, "reddit_client_id"),
        "client_secret": _sanitize_credential(cfg.client_secret, "reddit_client_secret"),
        "user_agent": _sanitize_credential(cfg.user_agent, "reddit_user_agent"),
    }
    if cfg.username and cfg.password:
        # User-Authentifizierung (grant_type=password) — benötigt für NSFW-Subreddits
        # wie r/wallstreetbets. Ohne username/password gibt Reddit 403 zurück.
        kwargs["username"] = _sanitize_credential(cfg.username, "reddit_username")
        kwargs["password"] = _sanitize_credential(cfg.password, "reddit_password")
        logger.debug("Reddit: Authentifizierung als Benutzer '{}'", cfg.username)
    else:
        logger.debug("Reddit: Application-only OAuth (kein username/password gesetzt)")
    return asyncpraw.Reddit(**kwargs)


async def _fetch_posts(
    reddit: asyncpraw.Reddit,
    subreddit_name: str,
    limit: int,
    comments_limit: int,
) -> tuple[list[RedditPost], list[RedditPost]]:
    """
    Holt Posts + Kommentare eines Subreddits.
    Gibt (posts, comments) zurück.
    """
    posts: list[RedditPost] = []
    comments: list[RedditPost] = []

    subreddit = await reddit.subreddit(subreddit_name)

    listing = subreddit.hot(limit=limit)
    try:
        async for submission in listing:
            post = RedditPost(
                id=submission.id,
                subreddit=subreddit_name,
                title=submission.title,
                text=submission.selftext or "",
                author=str(submission.author) if submission.author else "[deleted]",
                score=submission.score,
                upvote_ratio=submission.upvote_ratio,
                created_utc=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
                url=f"https://reddit.com{submission.permalink}",
                is_comment=False,
            )
            posts.append(post)

            # Top-Kommentare holen (nicht alle – zu viele API-Calls)
            if comments_limit > 0:
                submission.comment_sort = "top"
                await submission.load()
                submission.comments.replace_more(limit=0)  # MoreComments überspringen

                for comment in list(submission.comments)[:comments_limit]:
                    if not hasattr(comment, "body"):
                        continue
                    comments.append(
                        RedditPost(
                            id=comment.id,
                            subreddit=subreddit_name,
                            title="",
                            text=comment.body,
                            author=str(comment.author) if comment.author else "[deleted]",
                            score=comment.score,
                            upvote_ratio=0.0,
                            created_utc=datetime.fromtimestamp(
                                comment.created_utc, tz=timezone.utc
                            ),
                            url=f"https://reddit.com{submission.permalink}{comment.id}/",
                            is_comment=True,
                            parent_id=submission.id,
                        )
                    )
    except Exception:
        raise

    logger.debug(
        f"r/{subreddit_name}: {len(posts)} Posts, {len(comments)} Kommentare gelesen"
    )
    return posts, comments


async def crawl_all_subreddits(run_id: str) -> CrawlResult:
    """
    Crawlt alle konfigurierten Subreddits parallel.

    Gibt ein vollständiges CrawlResult zurück mit aggregierten
    Mention-Counts und allen Einzel-Mentions.
    """
    cfg = await get_settings(_db)
    crawler_cfg = cfg.crawler
    started_at = datetime.utcnow()

    all_posts: list[RedditPost] = []
    all_comments: list[RedditPost] = []

    async with _make_reddit_client(cfg.reddit) as reddit:
        # Alle Subreddits gleichzeitig crawlen (asyncio.gather)
        tasks = [
            _fetch_posts(
                reddit,
                sub,
                limit=crawler_cfg.posts_limit,
                comments_limit=crawler_cfg.comments_limit,
            )
            for sub in crawler_cfg.subreddits
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            sub = crawler_cfg.subreddits[i]
            if isinstance(result, asyncprawcore.exceptions.Forbidden):
                logger.error(
                    "Reddit 403 bei r/{}: {}. Bitte Reddit-API-Config prüfen "
                    "(client_id, client_secret, user_agent) und sicherstellen, dass die App als 'script' erstellt wurde.",
                    sub,
                    result,
                )
            else:
                logger.error(f"Fehler beim Crawlen von r/{sub}: {result}")
            continue
        posts, comments = result
        all_posts.extend(posts)
        all_comments.extend(comments)

    logger.info(
        f"Crawl abgeschlossen: {len(all_posts)} Posts, "
        f"{len(all_comments)} Kommentare aus {len(crawler_cfg.subreddits)} Subreddits"
    )

    # Ticker aus allen Posts + Kommentaren extrahieren
    all_items = all_posts + all_comments
    all_mentions: list[TickerMention] = []
    for item in all_items:
        all_mentions.extend(extract_tickers(item))

    mention_counts = aggregate_mentions(all_mentions)

    logger.info(f"Ticker erkannt: {len(mention_counts)} einzigartige Ticker")
    if mention_counts:
        top5 = list(mention_counts.items())[:5]
        logger.debug(f"Top 5: {top5}")

    return CrawlResult(
        run_id=run_id,
        started_at=started_at,
        subreddits=cfg.crawler.subreddits,
        posts_scanned=len(all_posts),
        comments_scanned=len(all_comments),
        mention_counts=mention_counts,
        mentions=all_mentions,
    )
