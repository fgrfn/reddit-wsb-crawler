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

def main():
    parser = argparse.ArgumentParser(description='Preview or send a test Discord message')
    parser.add_argument('--send', action='store_true', help='Actually send the message')
    parser.add_argument('--webhook', type=str, help='Discord webhook URL (overrides ENV)')
    parser.add_argument('--ticker', type=str, default='AAPL', help='Ticker symbol to use in test message')
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

    msg = build_test_message(
        ticker=args.ticker,
        nennungen=args.nennungen,
        company=args.company,
        price=args.price,
        change=args.change,
        change_percent=args.change_percent,
        summary=args.summary,
    )
    print('--- Preview Discord Message ---')
    print(msg)
    print('--- End Preview ---')

    if send_flag:
        print('Sending to webhook...' + (f' {webhook}' if webhook else ' (from ENV)'))
        ok = send_test_notification(webhook_url=webhook,
                                   ticker=args.ticker,
                                   nennungen=args.nennungen,
                                   company=args.company,
                                   price=args.price,
                                   change=args.change,
                                   change_percent=args.change_percent,
                                   summary=args.summary)
        print('Sent' if ok else 'Send failed')

if __name__ == '__main__':
    main()
