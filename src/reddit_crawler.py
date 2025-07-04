import os
import re
import pickle
import praw
import pandas as pd
import logging
import time
import requests
import yfinance as yf

from tqdm import tqdm
from datetime import datetime, timedelta, timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# 📁 Pfade
TICKER_CACHE_PATH = os.path.join("data", "input", "ticker_name_map.pkl")
TICKER_CSV_PATH = os.path.join("data", "input", "ticker_name_map.csv")
SYMBOLS_PATH = os.path.join("data", "input", "symbols_list.pkl")
LATEST_HITS_PATH = os.path.join("data", "output", "latest_ticker_hits.pkl")

# 🧠 Cache laden/speichern
def load_ticker_name_map():
    if os.path.exists(TICKER_CACHE_PATH):
        with open(TICKER_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    return {}

def save_ticker_name_map(name_map):
    with open(TICKER_CACHE_PATH, "wb") as f:
        pickle.dump(name_map, f)
    pd.DataFrame.from_dict(name_map, orient="index", columns=["Company"]).to_csv(TICKER_CSV_PATH)

# 🔍 (Optional) Name sofort auflösen
def fetch_name_with_retry(symbol, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            info = yf.Ticker(symbol).info
            name = info.get("longName") or info.get("shortName")
            if name and name != symbol:
                return symbol, name
        except Exception:
            pass
        if attempt < retries:
            time.sleep(delay * attempt)
    # Der alternative Yahoo-Request kommt NACH der Schleife!
    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.ok:
            for res in r.json().get("quotes", []):
                if res.get("symbol") == symbol and res.get("shortname"):
                    return symbol, res["shortname"]
    except Exception:
        pass
    return symbol, None

# Logging mit Emoji direkt im String
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/crawler.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 🕷️ Reddit-Crawler
def reddit_crawler():
    logger.info("🕷️ Crawl gestartet")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dotenv_path = os.path.join(base_dir, "..", "config", ".env")
    load_dotenv(dotenv_path)

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT")
    )

    if not os.path.exists(SYMBOLS_PATH):
        logger.error("symbols_list.pkl fehlt.")
        return

    with open(SYMBOLS_PATH, "rb") as f:
        symbols = pickle.load(f)

    blacklist = {'AI', 'IT', 'TV', 'NO', 'GO', 'BE', 'SO', 'OP', 'DD'}
    symbols = [s for s in symbols if s not in blacklist]

    subreddits = [s.strip() for s in os.getenv("SUBREDDITS", "wallstreetbets").split(",")]
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    run_id = datetime.now().strftime("%y%m%d-%H%M%S")
    logger.info(f"Run-ID: {run_id}")

    results = {}
    total_counter = Counter()

    for sr in subreddits:
        sr_data = reddit.subreddit(sr)
        counter = Counter()
        total_posts = 0
        logger.info(f"r/{sr} analysieren ...")
        for post in tqdm(sr_data.new(limit=100), desc=f"{sr}", unit="Post", ncols=80):
            try:
                if datetime.fromtimestamp(post.created_utc, tz=timezone.utc) < cutoff:
                    continue
                total_posts += 1
                text = f"{post.title} {post.selftext or ''}"
                post.comments.replace_more(limit=0)
                for comment in post.comments.list():
                    if hasattr(comment, "body") and isinstance(comment.body, str):
                        text += " " + comment.body
                text = text[:50000]
                for sym in symbols:
                    if re.search(rf"(?<!\w)(\${sym}|{sym})(?!\w)", text):
                        counter[sym] += 1
            except Exception:
                continue
        results[sr] = {
            "symbol_hits": dict(counter),
            "posts_checked": total_posts
        }
        total_counter.update(counter)

    # 🧠 Speichere Treffer für spätere Namensauflösung
    os.makedirs("data/output", exist_ok=True)
    with open(LATEST_HITS_PATH, "wb") as f:
        pickle.dump(total_counter, f)
    logger.info(f"Treffer gespeichert in: {LATEST_HITS_PATH}")

    relevant = {sym: count for sym, count in total_counter.items() if count > 5}

    os.makedirs("data/output/pickle", exist_ok=True)
    out_path = f"data/output/pickle/{run_id}_crawler-ergebnis.pkl"
    with open(out_path, "wb") as f:
        pickle.dump({
            "run_id": run_id,
            "subreddits": results,
            "relevant": relevant,
            "total_posts": sum(r["posts_checked"] for r in results.values())
        }, f)

    logger.info(f"Ergebnis gespeichert: {out_path}")
    if relevant:
        logger.info("Relevante Ticker:")
        for sym, count in sorted(relevant.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"   {sym}: {count}")
    else:
        logger.info("Keine relevanten Ticker gefunden.")