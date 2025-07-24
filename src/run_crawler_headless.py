import os
import sys
import time
import logging
import pickle
import yfinance as yf
import subprocess
import concurrent.futures
from datetime import datetime, timedelta
from tqdm import tqdm

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
STATS_PATH = BASE_DIR / "data" / "output" / "ticker_stats.pkl"  # <--- NEU

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
        if diff > 0:
            trend = f"▲ (+{diff})"
        elif diff < 0:
            trend = f"▼ ({diff})"
        else:
            trend = "→ (0)"
        emoji = platz_emojis[i-1] if i <= 3 else ""
        kurs = row.get('Kurs')
        marktstatus = row.get('Marktstatus')
        if kurs is not None:
            kurs_str = f"{kurs:.2f} USD"
            if marktstatus:
                kurs_str += f" ({marktstatus})"
            else:
                kurs_str += " (±0.00 USD)"  # <--- Hier geändert
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

def get_yf_price(symbol):
    try:
        symbol = symbol.lstrip("$")
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get("regularMarketPrice")
        pre = info.get("preMarketPrice")
        post = info.get("postMarketPrice")
        return float(price) if price is not None else None, \
               float(pre) if pre is not None else None, \
               float(post) if post is not None else None
    except Exception as e:
        logger.warning(f"Kursabfrage für {symbol} fehlgeschlagen: {e}")
        return None, None, None

def get_yf_price_hour_ago(symbol):
    try:
        symbol = symbol.lstrip("$")  # $ entfernen, falls vorhanden
        ticker = yf.Ticker(symbol)
        end = datetime.now()
        start = end - timedelta(hours=1, minutes=5)  # 5 Minuten Puffer
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
    except Exception as e:
        logger.warning(f"Kursabfrage (1h alt) für {symbol} fehlgeschlagen: {e}")
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

    # --- KI-Zusammenfassungen parallel erzeugen ---
    try:
        from utils import load_pickle, load_ticker_names  # <--- Import ergänzen
        import summarizer
        pickle_files = list_pickle_files(PICKLE_DIR)
        if not pickle_files:
            logger.warning("Keine Pickle-Datei für Zusammenfassung gefunden.")
        else:
            latest_pickle = sorted(pickle_files)[-1]
            logger.info(f"Starte parallele KI-Zusammenfassungen für: {latest_pickle}")
            # Hole die Top 3 Ticker
            import pandas as pd
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
            top3_ticker = df_ticker["Ticker"].head(3).tolist()

            # Parallele Zusammenfassung für Top 3
            from concurrent.futures import ThreadPoolExecutor, as_completed
            summary_dict = {}
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(
                        summarizer.generate_summary,
                        pickle_path=PICKLE_DIR / latest_pickle,
                        include_all=False,
                        streamlit_out=None,
                        only_symbols=[ticker]
                    ): ticker for ticker in top3_ticker
                }
                for future in as_completed(futures):
                    ticker = futures[future]
                    try:
                        summary = future.result()
                        summary_dict[ticker.upper()] = summary  # <--- Key immer upper
                    except Exception as e:
                        summary_dict[ticker.upper()] = f"Fehler: {e}"
            logger.info("Parallele KI-Zusammenfassungen abgeschlossen.")
    except Exception as e:
        logger.error(f"Fehler bei der parallelen KI-Zusammenfassung: {e}")
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

        # --- Parallelisierte Kursabfrage für Top 3 Ticker ---
        top3_ticker = df_ticker["Ticker"].head(3).tolist()
        t_kurse_start = time.time()
        kurse, kursdiffs = get_kurse_parallel(top3_ticker)
        t_kurse_ende = time.time()
        logger.info(f"Kursabfrage für Top 3 Ticker dauerte {t_kurse_ende - t_kurse_start:.2f} Sekunden")

        for ticker in top3_ticker:
            regular, pre, post = kurse.get(ticker, (None, None, None))
            marktstatus = None
            kurs = regular
            if pre is not None and pre != regular:
                kurs = pre
                marktstatus = "Pre-Market"
            elif post is not None and post != regular:
                kurs = post
                marktstatus = "After-Market"
            df_ticker.loc[df_ticker["Ticker"] == ticker, "Kurs"] = kurs
            df_ticker.loc[df_ticker["Ticker"] == ticker, "Marktstatus"] = marktstatus
            df_ticker.loc[df_ticker["Ticker"] == ticker, "KursRegular"] = regular

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
        archive_log(LOG_PATH, ARCHIVE_DIR)
    except Exception as e:
        logger.error(f"Fehler bei der Discord-Benachrichtigung: {e}")

    # --- Performance-Metriken loggen ---
    t_end = time.time()
    logger.info(
        f"Laufzeit: ENV={t_env-t0:.2f}s, Stats={t_stats-t_env:.2f}s, "
        f"Ticker={t_ticker-t_stats:.2f}s, Crawl={t_crawl-t_ticker:.2f}s, "
        f"Resolver={t_resolver-t_crawl:.2f}s, Summary={t_summary-t_resolver:.2f}s, "
        f"Kurse={t_kurse_ende-t_kurse_start:.2f}s, Discord={t_end-t_kurse_ende:.2f}s, Gesamt={t_end-t0:.2f}s"
    )

def get_next_systemd_run(timer_name="reddit_crawler.timer"):
    try:
        result = subprocess.run(
            ["systemctl", "list-timers", timer_name, "--no-legend", "--all"],
            capture_output=True, text=True
        )
        line = result.stdout.strip().splitlines()
        if line:
            logger.info(f"Systemd-Timer-Rohzeile: {line[0]}")
            parts = line[0].split()
            # Prüfe, ob mindestens drei Spalten vorhanden sind und das Datum wie erwartet aussieht
            if len(parts) >= 3 and "-" in parts[1] and ":" in parts[2]:
                try:
                    dt = datetime.strptime(f"{parts[1]} {parts[2]}", "%Y-%m-%d %H:%M:%S")
                    next_time = dt.strftime("%d.%m.%Y %H:%M:%S")
                except Exception:
                    logger.warning(f"Unerwartetes Zeitformat in systemd-Timer: {parts}")
                    next_time = "unbekannt"
                return next_time
            else:
                logger.warning(f"Systemd-Timer-Ausgabe unerwartet: {line[0]}")
    except Exception as e:
        logger.warning(f"Fehler beim Auslesen des systemd-Timers: {e}")
    return "unbekannt"

def get_kurse_parallel(ticker_list):
    kurse = {}
    kursdiffs = {}
    tickers_ohne_kurs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_ticker = {executor.submit(get_yf_price, t): t for t in ticker_list}
        future_to_ticker_ago = {executor.submit(get_yf_price_hour_ago, t): t for t in ticker_list}
        results = {}
        results_ago = {}
        for future in concurrent.futures.as_completed(future_to_ticker):
            t = future_to_ticker[future]
            try:
                results[t] = future.result()
            except Exception as e:
                logger.warning(f"Kursabfrage für {t} fehlgeschlagen: {e}")
                results[t] = None
        for future in concurrent.futures.as_completed(future_to_ticker_ago):
            t = future_to_ticker_ago[future]
            try:
                results_ago[t] = future.result()
            except Exception as e:
                logger.warning(f"Kursabfrage (1h alt) für {t} fehlgeschlagen: {e}")
                results_ago[t] = None
        for t in ticker_list:
            kurse[t] = results.get(t)
            kurs_ago = results_ago.get(t)
            if kurse[t] is not None and kurs_ago is not None:
                kursdiffs[t] = kurse[t] - kurs_ago
            else:
                kursdiffs[t] = None
                if kurse[t] is None or kurs_ago is None:
                    tickers_ohne_kurs.append(t)
    if tickers_ohne_kurs:
        logger.warning(f"Keine Kursdaten für folgende Ticker verfügbar: {', '.join(tickers_ohne_kurs)}")
    return kurse, kursdiffs

def crawl_subreddit(sr, reddit, symbols, cutoff, sr_idx=1, total_subs=1):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    sr_data = reddit.subreddit(sr)
    tqdm_desc = f"[{sr_idx}/{total_subs}] r/{sr}"
    posts = list(sr_data.new(limit=100))
    total_posts = len(posts)
    counters = []
    # Define subreddits list before using it
    subreddits = [sr]  # or provide a list of subreddit names as needed
    import collections
    results = {}  # <--- Fix: results initialisieren
    total_counter = collections.Counter()  # <--- Fix: total_counter initialisieren
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(crawl_subreddit, sr, reddit, symbols, cutoff, i+1, total_subs)
            for i, sr in enumerate(subreddits)
        ]
        for future in as_completed(futures):
            sr, sr_result = future.result()
            results[sr] = sr_result
            total_counter.update(sr_result["symbol_hits"])
    # ...restlicher Code...

if __name__ == "__main__":
    main()