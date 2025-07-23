import os
import sys
import time
import logging
import pickle
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

def format_discord_message(pickle_name, timestamp, df_ticker, prev_nennungen, name_map, summary_dict):
    platz_emojis = ["🥇", "🥈", "🥉"]
    msg = (
        f"🕷️ Crawl abgeschlossen! "
        f"📦 Datei: {pickle_name} "
        f"🕒 Zeitpunkt: {timestamp}\n\n"
        f"🏆 Top 3 Ticker:\n"
    )
    for i, (_, row) in enumerate(df_ticker.head(3).iterrows(), 1):
        ticker = row["Ticker"]
        nennungen = row["Nennungen"]
        diff = nennungen - prev_nennungen.get(ticker, 0)
        if diff > 0:
            trend = f"▲ (+{diff})"
        elif diff < 0:
            trend = f"▼ ({diff})"
        else:
            trend = "→ (0)"
        emoji = platz_emojis[i-1] if i <= 3 else ""
        kurs = row.get('Kurs')
        kurs_str = f"{kurs:.2f} USD" if kurs is not None else "k.A."
        unternehmen = row.get('Unternehmen', '') or name_map.get(ticker, '')
        msg += (
            f"\n{emoji} {ticker} - {unternehmen}\n"
            f"🔢 Nennungen: {nennungen} {trend}\n"
            f"💹 Kurs: {kurs_str}\n"
            f"🧠 Zusammenfassung:\n"
        )
        summary = summary_dict.get(ticker)
        if summary:
            msg += summary.strip() + "\n"
        msg += "\n"
    return msg

def main():
    logger.info("🔄 Lade Umgebungsvariablen ...")
    load_dotenv(ENV_PATH)

    # --- Tickerliste aktualisieren ---
    try:
        from ticker_utils import download_and_clean_tickerlist
        tickers = download_and_clean_tickerlist()
        logger.info(f"Tickerliste geladen: {len(tickers)} Einträge")
        SYMBOLS_PKL.parent.mkdir(parents=True, exist_ok=True)
        with open(SYMBOLS_PKL, "wb") as f:
            pickle.dump(list(tickers["Symbol"]), f)
    except Exception as e:
        logger.error(f"Fehler beim Laden der Tickerliste: {e}")

    # --- Crawl starten ---
    try:
        logger.info("🕷️ Starte Reddit-Crawler ...")
        from reddit_crawler import reddit_crawler
        reddit_crawler()
        logger.info("✅ Crawl abgeschlossen")
    except Exception as e:
        logger.error(f"Fehler beim Reddit-Crawl: {e}")

    # --- Ticker-Namensauflösung ---
    try:
        logger.info("📡 Starte Ticker-Namensauflösung ...")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(NAME_RESOLVER_SCRIPT)],
            capture_output=True, text=True
        )
        logger.info(result.stdout)
        if result.returncode == 0:
            logger.info("Namensauflösung abgeschlossen!")
        else:
            logger.error("Fehler bei der Namensauflösung.")
    except Exception as e:
        logger.error(f"Fehler beim Resolver: {e}")

    # --- KI-Zusammenfassung erzeugen ---
    try:
        from utils import list_pickle_files
        import summarizer
        pickle_files = list_pickle_files(PICKLE_DIR)
        if not pickle_files:
            logger.warning("Keine Pickle-Datei für Zusammenfassung gefunden.")
        else:
            latest_pickle = sorted(pickle_files)[-1]
            logger.info(f"Starte KI-Zusammenfassung für: {latest_pickle}")
            summarizer.generate_summary(
                pickle_path=PICKLE_DIR / latest_pickle,
                include_all=False,
                streamlit_out=None,
                only_symbols=None
            )
            logger.info("KI-Zusammenfassung abgeschlossen.")
    except Exception as e:
        logger.error(f"Fehler bei der KI-Zusammenfassung: {e}")

    # --- Discord-Benachrichtigung ---
    try:
        import pandas as pd
        from utils import list_pickle_files, load_pickle, load_ticker_names, find_summary_for, load_summary, parse_summary_md
        pickle_files = list_pickle_files(PICKLE_DIR)
        if not pickle_files:
            logger.warning("Keine Pickle-Datei gefunden, keine Benachrichtigung möglich.")
            return
        latest_pickle = sorted(pickle_files)[-1]
        result = load_pickle(PICKLE_DIR / latest_pickle)
        name_map = load_ticker_names(TICKER_NAME_PATH)
        df_rows = []
        for subreddit, srdata in result.get("subreddits", {}).items():
            for symbol, count in srdata["symbol_hits"].items():
                df_rows.append({
                    "Ticker": symbol,
                    "Subreddit": subreddit,
                    "Nennungen": count,
                    "Kurs": srdata.get("price", {}).get(symbol),
                })
        df = pd.DataFrame(df_rows)
        df["Unternehmen"] = df["Ticker"].map(name_map)
        df_ticker = (
            df.groupby(["Ticker", "Unternehmen"], as_index=False)["Nennungen"]
            .sum()
            .sort_values(by="Nennungen", ascending=False)
        )
        # Trend-Berechnung
        if len(pickle_files) >= 2:
            prev_pickle = sorted(pickle_files)[-2]
            prev_result = load_pickle(PICKLE_DIR / prev_pickle)
            prev_rows = []
            for subreddit, srdata in prev_result.get("subreddits", {}).items():
                for symbol, count in srdata["symbol_hits"].items():
                    prev_rows.append({"Ticker": symbol, "Nennungen": count})
            prev_df = pd.DataFrame(prev_rows)
            prev_nennungen = prev_df.groupby("Ticker")["Nennungen"].sum().to_dict()
        else:
            prev_nennungen = {}

        summary_path = find_summary_for(latest_pickle, SUMMARY_DIR)
        summary_dict = {}
        if summary_path and summary_path.exists():
            summary_text = load_summary(summary_path)
            summary_dict = parse_summary_md(summary_text)

        timestamp = time.strftime("%d.%m.%Y %H:%M:%S")
        msg = format_discord_message(
            pickle_name=latest_pickle,
            timestamp=timestamp,
            df_ticker=df_ticker,
            prev_nennungen=prev_nennungen,
            name_map=name_map,
            summary_dict=summary_dict
        )
        success = send_discord_notification(msg)
        if success:
            logger.info("Discord-Benachrichtigung gesendet!")
        else:
            logger.error("Fehler beim Senden der Discord-Benachrichtigung.")
    except Exception as e:
        logger.error(f"Fehler bei der Discord-Benachrichtigung: {e}")

    # --- Logfile archivieren ---
    try:
        archive_log(LOG_PATH, ARCHIVE_DIR)
    except Exception as e:
        logger.warning(f"Fehler beim Log-Archiv: {e}")

if __name__ == "__main__":