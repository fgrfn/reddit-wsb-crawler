"""Interaktives Tool zum Prüfen von Ticker-Erwähnungen auf Reddit."""
import praw
import re
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

def search_ticker(ticker: str) -> tuple[int, list[dict]]:
    """Sucht nach einem Ticker-Symbol in r/wallstreetbets.
    
    Args:
        ticker: Ticker-Symbol zum Suchen (z.B. "GME")
    
    Returns:
        tuple: (total_hits, results_list) mit total_hits als int und results_list als Liste von Dicts
    """
    load_dotenv()

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT")
    )

    subreddit = reddit.subreddit("wallstreetbets")
    since = datetime.now(timezone.utc) - timedelta(days=1)

    pattern = re.compile(rf"(?<!\w)(\${ticker}|{ticker})(?!\w)")

    total = 0
    results = []

    for post in subreddit.new(limit=100):
        if datetime.fromtimestamp(post.created_utc, tz=timezone.utc) < since:
            continue

        text = f"{post.title}\n{post.selftext or ''}"
        post_hits = pattern.findall(text)

        comment_hits = []
        try:
            post.comments.replace_more(limit=0)
            for comment in post.comments.list():
                comment_hits.extend(pattern.findall(comment.body))
        except Exception:
            pass

        count = len(post_hits) + len(comment_hits)
        if count > 0:
            total += count
            results.append({
                "title": post.title,
                "url": f"https://reddit.com{post.permalink}",
                "post_hits": len(post_hits),
                "comment_hits": len(comment_hits),
                "upvotes": post.score,
                "comments": post.num_comments,
                "variants": {v: (post_hits + comment_hits).count(v) for v in set(post_hits + comment_hits)}
            })

    return total, results

def main():
    print("🔎 Reddit-Kontrollanalyse")
    while True:
        ticker = input("\n▶️  Tickersymbol eingeben (oder 'quit'): ").strip().upper()
        if ticker == "QUIT":
            print("👋 Bis bald.")
            break

        total, results = search_ticker(ticker)
        print(f"\n=== Ergebnisse für '{ticker}' ===")
        print(f"Gesamttreffer: {total} | Beiträge gefunden: {len(results)}")

        for i, res in enumerate(results, 1):
            print(f"\n[{i}] {res['title']}")
            print(f"🔗 {res['url']}")
            print(f"👍 Upvotes: {res['upvotes']} | 💬 Kommentare: {res['comments']}")
            print(f"🎯 Treffer – Post: {res['post_hits']} | Kommentare: {res['comment_hits']}")
            print("🧬 Varianten:", ", ".join([f"{k}: {v}×" for k, v in res['variants'].items()]))

if __name__ == "__main__":
    main()
