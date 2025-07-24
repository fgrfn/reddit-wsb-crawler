import os
import sys
import time
import logging
import pickle
import yfinance as yf
import subprocess
import concurrent.futures
from datetime import datetime, timedelta

from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
os.chdir(BASE_DIR)
LOG_PATH = BASE_DIR / "logs" / "crawler.log"
ARCHIVE_DIR = BASE_DIR / "logs" / "archive"
ENV_PATH = BASE_DIR / "config" / ".env"
SYMBOLS_PKL = BASE_DIR / "data" / "input" / "symbols_list.pkl"
NAME_RESOLVER_SCRIPT = BASE_DIR / "src" / "build_ticker_name_cache.py"
PICKLE_DIR = BASE_DIR / "data" / "output" / "pickle"
SUMMARY_DIR = BASE_DIR / "data" / "output" / "summaries"
TICKER_NAME_PATH = BASE_DIR / "data" / "input" / "ticker_name_map.pkl"
STATS_PATH = BASE_DIR / "data" / "output" / "ticker_stats.pkl"

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8", delay=False),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def archive_log(log_path, archive_dir):
    import shutil
    from datetime import datetime
    if not log_path.exists():
        return
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_file = archive_dir / f"{log_path.stem}_{ts}.log"
    shutil.copy(str(log_path), str(archive_file))
    logger.info(f"Logfile archiviert: {archive_file}")

def send_discord_notification(message, webhook_url=None):
    import requests
    if webhook_url is None:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("Kein Discord-Webhook-URL gesetzt.")
        return False
    try:
        data = {"content": message}
        response = requests.post(webhook_url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ Discord-Benachrichtigung fehlgeschlagen: {e}")
        return False

def format_discord_message(pickle_name, timestamp, df_ticker, prev_nennungen, name_map, summary_dict, next_crawl_time=None):
    platz_emojis = ["🥇", "🥈", "🥉"]
    next_crawl_str = f"{next_crawl_time}" if next_crawl_time else "unbekannt"
    warntext = "… [gekürzt wegen Discord-Limit]"
    maxlen = 1900

    msg = (
        f"🕷️ Crawl abgeschlossen! "
        f"💾 {pickle_name} "
        f"🕒 {timestamp} ⏰ {next_crawl_str}\n\n"
        f"🏆 Top 3 Ticker:\n"
    )

    ticker_blocks = []
    for i, (_, row) in enumerate(df_ticker.head(3).iterrows(), 1):
        ticker = row["Ticker"]
        nennungen = row["Nennungen"]
        diff = nennungen - prev_nennungen.get(ticker, 0)
        trend = f"▲ (+{diff})" if diff > 0 else f"▼ ({diff})" if diff < 0 else "→ (0)"
        emoji = platz_emojis[i-1] if i <= 3 else ""
        kurs_str = row.get('KursStr', 'keine Kursdaten verfügbar')
        unternehmen = row.get('Unternehmen', '') or name_map.get(ticker, '')
        block = (
            f"\n{emoji} {ticker} - {unternehmen}\n"
            f"🔢 Nennungen: {nennungen} {trend}\n"
            f"💰 Kurs: {kurs_str}\n"
            f"🧠 Zusammenfassung:\n"
        )
        summary = summary_dict.get(ticker.strip().upper())
        if summary:
            block += summary.strip() + "\n"
        block += "\n"
        ticker_blocks.append(block)

    for i, block in enumerate(ticker_blocks):
        if i < 2:
            msg += block
        else:
            if len(msg) + len(block) > maxlen:
                msg += warntext
                break
            msg += block

    if len(msg) > 2000:
        msg = msg[:2000 - len(warntext)] + warntext

    return msg

# Die restlichen Funktionen bleiben unverändert, da sie bereits optimiert sind.

if __name__ == "__main__":
    main()