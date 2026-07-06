"""
Async Reddit-Crawling via asyncpraw.

asyncpraw ist der offizielle async-Port von praw. Alle Netzwerk-Calls
sind awaitable, was paralleles Crawlen mehrerer Subreddits ermöglicht.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import asyncpraw
import asyncprawcore
from loguru import logger

from wsb_crawler.config import RedditSettings, get_settings
from wsb_crawler.crawler.ticker import aggregate_mentions, extract_tickers
from wsb_crawler.models import CrawlResult, RedditPost, TickerMention
from wsb_crawler.runtime.progress import update_run, update_subreddit

if TYPE_CHECKING:
    from wsb_crawler.storage.database import Database

_db: Database | None = None


def set_database(db: Database) -> None:
    global _db
    _db = db


def _get_db() -> Database:
    if _db is None:
        raise RuntimeError("Datenbank nicht gesetzt — set_database() zuerst aufrufen")
    return _db


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


def _make_reddit_client(cfg: RedditSettings) -> asyncpraw.Reddit:
    kwargs: dict[str, Any] = {
        "client_id": _sanitize_credential(cfg.client_id, "reddit_client_id"),
        "client_secret": _sanitize_credential(cfg.client_secret, "reddit_client_secret"),
        "user_agent": _sanitize_credential(cfg.user_agent, "reddit_user_agent"),
    }
    if cfg.username and cfg.password:
        # User-Authentifizierung (grant_type=password) — für NSFW-Subreddits empfohlen
        kwargs["username"] = _sanitize_credential(cfg.username, "reddit_username")
        kwargs["password"] = _sanitize_credential(cfg.password, "reddit_password")
        logger.debug("Reddit: Authentifizierung als Benutzer '{}'", cfg.username)
    else:
        # asyncpraw 7.7+ benötigt read_only=True für korrektes application-only OAuth
        # (client_credentials grant). Ohne dieses Flag versucht asyncpraw u.U. eine
        # User-Auth mit leeren Credentials → 403. praw (sync) setzt dies implizit.
        kwargs["read_only"] = True
        logger.debug("Reddit: Application-only OAuth (read_only=True)")
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

    update_subreddit(subreddit_name, posts=0, comments=0)
    logger.info(
        f"r/{subreddit_name}: lade bis zu {limit} Posts mit je {comments_limit} Top-Kommentaren"
    )

    subreddit = await reddit.subreddit(subreddit_name)

    async for submission in subreddit.hot(limit=limit):
        post = RedditPost(
            id=submission.id,
            subreddit=subreddit_name,
            title=submission.title,
            text=submission.selftext or "",
            author=str(submission.author) if submission.author else "[deleted]",
            score=submission.score,
            upvote_ratio=submission.upvote_ratio,
            created_utc=datetime.fromtimestamp(submission.created_utc, tz=UTC),
            url=f"https://reddit.com{submission.permalink}",
            is_comment=False,
        )
        posts.append(post)

        # Top-Kommentare holen (nicht alle – zu viele API-Calls)
        if comments_limit > 0:
            submission.comment_sort = "top"
            await submission.load()
            # replace_more ist in asyncpraw eine Coroutine — ohne await bleiben
            # MoreComments-Objekte im Baum und belegen Plätze im Limit-Slice
            await submission.comments.replace_more(limit=0)

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
                        created_utc=datetime.fromtimestamp(comment.created_utc, tz=UTC),
                        url=f"https://reddit.com{submission.permalink}{comment.id}/",
                        is_comment=True,
                        parent_id=submission.id,
                    )
                )

        if len(posts) % 25 == 0:
            update_subreddit(subreddit_name, posts=len(posts), comments=len(comments))
            logger.info(
                f"r/{subreddit_name}: Zwischenstand {len(posts)} Posts, "
                f"{len(comments)} Kommentare"
            )

    update_subreddit(subreddit_name, posts=len(posts), comments=len(comments), done=True)
    logger.info(f"r/{subreddit_name}: fertig — {len(posts)} Posts, {len(comments)} Kommentare")
    return posts, comments


async def crawl_all_subreddits(run_id: str) -> CrawlResult:
    """
    Crawlt alle konfigurierten Subreddits parallel.

    Gibt ein vollständiges CrawlResult zurück mit aggregierten
    Mention-Counts und allen Einzel-Mentions.
    """
    cfg = await get_settings(_get_db())
    crawler_cfg = cfg.crawler
    started_at = datetime.now(tz=UTC)

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
        sub = crawler_cfg.subreddits[i]
        if isinstance(result, BaseException):
            update_subreddit(sub, posts=0, comments=0, done=True, error=str(result))
            if isinstance(result, asyncprawcore.exceptions.Forbidden):
                logger.error(
                    "Reddit 403 bei r/{}: {}. Bitte Reddit-API-Config prüfen "
                    "(client_id, client_secret, user_agent) und sicherstellen, "
                    "dass die App als 'script' erstellt wurde.",
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
    update_run(
        phase="extract",
        phase_label="Ticker erkennen",
        message=f"Extrahiere Ticker aus {len(all_items)} Reddit-Beiträgen und Kommentaren…",
        progress=42,
        posts_scanned=len(all_posts),
        comments_scanned=len(all_comments),
    )
    all_mentions: list[TickerMention] = []
    for idx, item in enumerate(all_items, start=1):
        all_mentions.extend(extract_tickers(item))
        if idx % 2500 == 0:
            update_run(
                message=f"Ticker-Erkennung: {idx}/{len(all_items)} Texte verarbeitet…",
                progress=42 + int((idx / max(1, len(all_items))) * 6),
            )

    mention_counts = aggregate_mentions(all_mentions)
    top_tickers = list(mention_counts.items())[:10]

    update_run(
        phase="extract",
        phase_label="Ticker erkennen",
        message=f"{len(mention_counts)} einzigartige Ticker erkannt.",
        progress=49,
        tickers_found=len(mention_counts),
        top_tickers=top_tickers,
    )

    logger.info(f"Ticker erkannt: {len(mention_counts)} einzigartige Ticker")
    if mention_counts:
        logger.info(f"Top-Ticker: {top_tickers[:5]}")

    return CrawlResult(
        run_id=run_id,
        started_at=started_at,
        finished_at=datetime.now(tz=UTC),
        subreddits=cfg.crawler.subreddits,
        posts_scanned=len(all_posts),
        comments_scanned=len(all_comments),
        mention_counts=mention_counts,
        mentions=all_mentions,
    )
