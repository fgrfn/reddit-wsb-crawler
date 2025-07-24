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

# --- NEU: Log-Rotation ---
from logging.handlers import RotatingFileHandler

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
STATS_PATH = BASE_DIR / "data" / "output" / "ticker_stats.pkl"  # <--- NEU

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# --- NEU: RotatingFileHandler verwenden ---
log_formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
file_handler = RotatingFileHandler(LOG_PATH, maxBytes=2*1024*1024, backupCount=5, encoding="utf-8", delay=False)
file_handler.setFormatter(log_formatter)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
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
        if diff > 0:
            trend = f"▲ (+{diff})"
        elif diff < 0:
            trend = f"▼ ({diff})"
        else:
            trend = "→ (0)"
        emoji = platz_emojis[i-1] if i <= 3 else ""
        kurs = row.get('Kurs')
        kursdiff = row.get('Kursdiff')
        if kurs is not None:
            kurs_str = f"{kurs:.2f} USD"
            if kursdiff is not None and not (isinstance(kursdiff, float) and (kursdiff != kursdiff)):
                kurs_str += f" ({kursdiff:+.2f} USD)"
            else:
                kurs_str += " (keine Kursdifferenz verfügbar)"
        else:
            kurs_str = "keine Kursdaten verfügbar"
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

    # Füge die ersten beiden Ticker immer vollständig hinzu
    for i, block in enumerate(ticker_blocks):
        if i < 2:
            msg += block
        else:
            # Nur Nummer 3 ggf. kürzen
            if len(msg) + len(block) > maxlen - len(warntext):
                split_idx = block.find("🧠 Zusammenfassung:\n")
                if split_idx != -1:
                    head = block[:split_idx + len("🧠 Zusammenfassung:\n")]
                    summary = block[split_idx + len("🧠 Zusammenfassung:\n"):]
                    allowed = maxlen - len(msg) - len(warntext) - 2  # 2 für \n\n
                    summary = summary[:allowed] + warntext
                    block = head + summary + "\n\n"
                else:
                    block = block[:maxlen - len(msg) - len(warntext)] + warntext
            msg += block
            break

    # Endgültig auf Discord-Limit kürzen (falls z.B. die Basisdaten zu lang sind)
    if len(msg) > 2000:
        msg = msg[:2000 - len(warntext)] + warntext

    return msg

# --- NEU: Retry-Decorator ---
def retry(max_attempts=3, delay=2):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Fehler bei {func.__name__}({args}): {e} (Versuch {attempt}/{max_attempts})")
                    if attempt < max_attempts:
                        time.sleep(delay)
            return None
        return wrapper
    return decorator

# --- NEU: Retry für Kursabfragen ---
@retry(max_attempts=3, delay=2)
def get_yf_price(symbol):
    ticker = yf.Ticker(symbol)
    price = ticker.info.get("regularMarketPrice")
    return float(price) if price is not None else None

@retry(max_attempts=3, delay=2)
def get_yf_price_hour_ago(symbol):
    ticker = yf.Ticker(symbol)
    end = datetime.now()
    start = end - timedelta(hours=1, minutes=5)
    df = ticker.history(interval="1m", start=start, end=end)
    if not df.empty:
        target_time = end - timedelta(hours=1)
        df = df[df.index <= target_time]
        if not df.empty:
            price = df["Close"].iloc[-1]
            return float(price)
        else:
            price = df["Close"].iloc[0]
            return float(price)
    else:
        return None
def save_stats(stats_path, nennungen_dict, kurs_dict):
    with open(stats_path, "wb") as f:
        pickle.dump({"nennungen": nennungen_dict, "kurs": kurs_dict}, f)

def load_stats(stats_path):
    if not os.path.exists(stats_path):
        return {}, {}
    with open(stats_path, "rb") as f:
        data = pickle.load(f)
        return data.get("nennungen", {}), data.get("kurs", {})

def main():
    # --- NEU: Performance-Metriken ---
    t0 = time.time()
    logger.info("🔄 Lade Umgebungsvariablen ...")
    load_dotenv(ENV_PATH)
    t_env = time.time()

    prev_nennungen, prev_kurse = load_stats(STATS_PATH)
    t_stats = time.time()

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
    t_ticker = time.time()

    # --- Crawl starten ---
    try:
        logger.info("🕷️  Starte Reddit-Crawler ...")
        from reddit_crawler import reddit_crawler
        reddit_crawler()
        logger.info("✅ Crawl abgeschlossen")
    except Exception as e:
        logger.error(f"Fehler beim Reddit-Crawl: {e}")
    t_crawl = time.time()

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
    t_resolver = time.time()

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
    t_summary = time.time()

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

        # Kursdaten für die Top 3 Ticker holen
        top3_ticker = df_ticker["Ticker"].head(3).tolist()
        kurse, kursdiffs = get_kurse_parallel(top3_ticker)
        for ticker in top3_ticker:
            df_ticker.loc[df_ticker["Ticker"] == ticker, "Kurs"] = kurse.get(ticker)
            df_ticker.loc[df_ticker["Ticker"] == ticker, "Kursdiff"] = kursdiffs.get(ticker)

        # Nach dem Erstellen von df_ticker:
        aktuelle_nennungen = dict(zip(df_ticker["Ticker"], df_ticker["Nennungen"]))
        aktuelle_kurse = dict(zip(df_ticker["Ticker"], df_ticker["Kurs"]))
        save_stats(STATS_PATH, aktuelle_nennungen, aktuelle_kurse)

        next_crawl_time = get_next_systemd_run()

        timestamp = time.strftime("%d.%m.%Y %H:%M:%S")
        msg = format_discord_message(
            pickle_name=latest_pickle,
            timestamp=timestamp,
            df_ticker=df_ticker,
            prev_nennungen=prev_nennungen,
            name_map=name_map,
            summary_dict=summary_dict,
            next_crawl_time=next_crawl_time
        )
        success = send_discord_notification(msg)
        if success:
            logger.info("Discord-Benachrichtigung gesendet!")
        else:
            logger.error("Fehler beim Senden der Discord-Benachrichtigung.")

        # --- NEU: Diagramm erzeugen und an Discord senden ---
        try:
            send_ticker_stats_plot(df_ticker, STATS_PATH)
        except Exception as e:
            logger.warning(f"Diagramm konnte nicht gesendet werden: {e}")

        # Logfile direkt nach Benachrichtigung archivieren!
        archive_log(LOG_PATH, ARCHIVE_DIR)
    except Exception as e:
        logger.error(f"Fehler bei der Discord-Benachrichtigung: {e}")

    # --- NEU: Performance-Metriken loggen ---
    t_end = time.time()
    logger.info(f"Laufzeit: ENV={t_env-t0:.2f}s, Stats={t_stats-t_env:.2f}s, Ticker={t_ticker-t_stats:.2f}s, Crawl={t_crawl-t_ticker:.2f}s, Resolver={t_resolver-t_crawl:.2f}s, Summary={t_summary-t_resolver:.2f}s, Discord={t_end-t_summary:.2f}s, Gesamt={t_end-t0:.2f}s")

# --- NEU: Diagramm-Funktion ---
def send_ticker_stats_plot(df_ticker, stats_path):
    import matplotlib.pyplot as plt
    import io
    import requests

    # Lade bisherige Statistik
    if os.path.exists(stats_path):
        with open(stats_path, "rb") as f:
            stats = pickle.load(f)
        nennungen_hist = stats.get("nennungen", {})
        kurs_hist = stats.get("kurs", {})
    else:
        nennungen_hist = {}
        kurs_hist = {}

    # Nur Top 3 Ticker plotten
    top3 = df_ticker["Ticker"].head(3).tolist()
    fig, ax1 = plt.subplots(figsize=(8, 4))
    for ticker in top3:
        y = [nennungen_hist.get(ticker, 0)]
        ax1.plot([0], y, marker="o", label=f"{ticker} Nennungen")
    ax1.set_ylabel("Nennungen")
    ax1.set_xlabel("Lauf")
    ax1.legend(loc="upper left")
    plt.title("Top 3 Ticker Nennungen (letzter Lauf)")
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    buf.seek(0)

    # Sende Bild an Discord
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if webhook_url:
        files = {"file": ("ticker_stats.png", buf, "image/png")}
        data = {"content": "📈 Ticker-Statistik (letzter Lauf)"}
        requests.post(webhook_url, data=data, files=files, timeout=10)
    plt.close(fig)