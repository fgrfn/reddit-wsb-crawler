import sys
from pathlib import Path

import os
from dotenv import load_dotenv

# Locate repository root by walking up until a directory containing 'src' is found.
script_dir = Path(__file__).resolve().parent
REPO_ROOT = None
for up in [script_dir] + list(script_dir.parents):
    if (up / 'src').is_dir():
        REPO_ROOT = up
        break
if REPO_ROOT is None:
    # fallback: assume parent of script_dir
    REPO_ROOT = script_dir.parent
SRC_DIR = REPO_ROOT / 'src'
import sys
# Ensure imports resolve to the project's src/ directory
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(REPO_ROOT))

# Run from repo root so relative imports and data paths behave predictably
try:
    os.chdir(str(REPO_ROOT))
except Exception:
    pass

from discord_utils import build_test_message, send_test_notification
import argparse

# Optional utils to load real crawl data
from utils import (
    list_pickle_files,
    load_pickle,
    load_ticker_names,
    find_summary_for,
    load_summary,
    parse_summary_md,
)
try:
    from summarize_ticker import get_yf_price
except Exception:
    get_yf_price = None

PICKLE_DIR = Path("data/output/pickle")
SUMMARY_DIR = Path("data/output/summaries")
TICKER_NAME_PATH = Path("data/input/ticker_name_map.pkl")

def pick_top_ticker_from_result(result):
    # Versuche zuerst 'relevant' (Ticker->count), sonst Aggregation aus subreddits
    if isinstance(result, dict):
        if "relevant" in result and isinstance(result["relevant"], dict) and result["relevant"]:
            sorted_relevant = sorted(result["relevant"].items(), key=lambda x: x[1], reverse=True)
            return sorted_relevant[0][0]
        # fallback: aggregate symbol_hits over subreddits
        total = {}
        for srdata in result.get("subreddits", {}).values():
            for sym, cnt in srdata.get("symbol_hits", {}).items():
                total[sym] = total.get(sym, 0) + int(cnt or 0)
        if total:
            return sorted(total.items(), key=lambda x: x[1], reverse=True)[0][0]
    return None

def build_from_real_data(preferred_ticker=None):
    pickle_files = list_pickle_files(PICKLE_DIR)
    if not pickle_files:
        return None  # keine echten Daten vorhanden
    latest = pickle_files[0]
    result = load_pickle(PICKLE_DIR / latest)
    ticker = preferred_ticker or pick_top_ticker_from_result(result) or "TEST"
    # Namen aus Cache
    name_map = load_ticker_names(TICKER_NAME_PATH)
    company = name_map.get(ticker, "")
    # summary: versuche passenden Summary-File zu finden
    summary = ""
    sum_path = find_summary_for(latest, SUMMARY_DIR)
    if sum_path:
        try:
            txt = load_summary(sum_path)
            parsed = parse_summary_md(txt)
            summary = parsed.get(ticker, "") or ""
        except Exception:
            summary = ""
    # price: optional per get_yf_price
    price = None
    change = None
    change_percent = None
    if get_yf_price:
        try:
            p = get_yf_price(ticker)
            price = p.get("regular")
            change = p.get("change")
            change_percent = p.get("changePercent")
        except Exception:
            price = None
    # nennungen: aus result (sum over subreddits) or relevant
    nennungen = 0
    if "relevant" in result and isinstance(result["relevant"], dict):
        nennungen = int(result["relevant"].get(ticker, 0))
    else:
        # aggregate
        for srdata in result.get("subreddits", {}).values():
            nennungen += int(srdata.get("symbol_hits", {}).get(ticker, 0) or 0)
    return {
        "ticker": ticker,
        "company": company,
        "nennungen": nennungen or 0,
        "price": price,
        "change": change,
        "change_percent": change_percent,
        "summary": summary,
        "pickle_name": latest,
    }

def main():
    parser = argparse.ArgumentParser(description='Preview or send a test Discord message')
    parser.add_argument('--send', action='store_true', help='Actually send the message')
    parser.add_argument('--webhook', type=str, help='Discord webhook URL (overrides ENV)')
    parser.add_argument('--ticker', type=str, default='', help='Ticker symbol to use in test message (override)')
    parser.add_argument('--use-real', action='store_true', help='Use real collected crawl data if available')
    parser.add_argument('--company', type=str, default='', help='Company name for test message (leave empty to auto-resolve from ticker map)')
    parser.add_argument('--nennungen', type=int, default=123, help='Number of mentions')
    parser.add_argument('--price', type=float, default=172.35, help='Price to show')
    parser.add_argument('--change', type=float, default=1.23, help='Absolute change to show')
    parser.add_argument('--change_percent', type=float, default=0.72, help='Percent change to show')
    parser.add_argument('--summary', type=str, default='Kurz: starke Diskussion auf Reddit, bullische Stimmung.', help='Summary text')
    args = parser.parse_args()

    send_flag = args.send
    webhook = args.webhook
    # If no webhook provided, try to load from config/.env
    if not webhook:
        env_path = REPO_ROOT / 'config' / '.env'
        if env_path.exists():
            load_dotenv(dotenv_path=str(env_path))
        webhook = os.getenv('DISCORD_WEBHOOK_URL')

    # Optionally use real collected data
    real = None
    if args.use_real:
        try:
            real = build_from_real_data(preferred_ticker=(args.ticker or None))
        except Exception:
            real = None

    if real:
        ticker = real["ticker"]
        company = args.company or real["company"] or ""
        nennungen = real["nennungen"]
        price = real["price"] if real["price"] is not None else args.price
        change = real["change"] if real["change"] is not None else args.change
        change_percent = real["change_percent"] if real["change_percent"] is not None else args.change_percent
        summary = real["summary"] or args.summary
        pickle_name = real.get("pickle_name", "test_payload.pkl")
    else:
        ticker = args.ticker or "AAPL"
        company = args.company
        nennungen = args.nennungen
        price = args.price
        change = args.change
        change_percent = args.change_percent
        summary = args.summary
        pickle_name = "test_payload.pkl"

    msg = build_test_message(
        ticker=ticker,
        nennungen=nennungen,
        company=company,
        price=price,
        change=change,
        change_percent=change_percent,
        summary=summary,
        pickle_name=pickle_name,
    )
    print('--- Preview Discord Message ---')
    print(msg)
    print('--- End Preview ---')

    if send_flag:
        print('Sending to webhook...' + (f' {webhook}' if webhook else ' (from ENV)'))
        ok = send_test_notification(webhook_url=webhook,
                                   ticker=ticker,
                                   nennungen=nennungen,
                                   company=company,
                                   price=price,
                                   change=change,
                                   change_percent=change_percent,
                                   summary=summary)
        print('Sent' if ok else 'Send failed')

if __name__ == '__main__':
    main()
