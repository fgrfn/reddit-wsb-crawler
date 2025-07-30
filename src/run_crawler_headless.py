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
from discord_utils import send_discord_notification, get_discord_legend, format_discord_message
from summarize_ticker import summarize_ticker, build_context_with_yahoo, get_yf_news

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

def get_yf_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        regular = info.get("regularMarketPrice")
        previous = info.get("previousClose")
        change = None
        changePercent = None
        if regular is not None and previous is not None:
            change = regular - previous
            changePercent = (change / previous) * 100 if previous != 0 else None
        return {
            "regular": float(regular) if regular is not None else None,
            "pre": float(info.get("preMarketPrice")) if info.get("preMarketPrice") is not None else None,
            "post": float(info.get("postMarketPrice")) if info.get("postMarketPrice") is not None else None,
            "previousClose": float(previous) if previous is not None else None,
            "change": float(change) if change is not None else None,
            "changePercent": float(changePercent) if changePercent is not None else None,
            "currency": info.get("currency", "USD"),
            "timestamp": info.get("regularMarketTime")  # Unix timestamp
        }
    except Exception as e:
        logger.warning(f"Kursabfrage für {symbol} fehlgeschlagen: {e}")
        return {"regular": None, "pre": None, "post": None, "previousClose": None, "change": None, "changePercent": None, "currency": "USD", "timestamp": None}

def save_stats(stats_path, nennungen_dict, kurs_dict):
    with open(stats_path, "wb") as f:
        pickle.dump({"nennungen": nennungen_dict, "kurs": kurs_dict}, f)

def load_stats(stats_path):
    if not os.path.exists(stats_path):
        return {}, {}
    with open(stats_path, "rb") as f:
        data = pickle.load(f)
        return data.get("nennungen", {}), data.get("kurs", {})

def post_daily_openai_cost():
    import pandas as pd
    from datetime import datetime
    log_path = Path("logs/openai_costs.log")
    if not log_path.exists():
        return
    today = datetime.now().strftime("%Y-%m-%d")
    total_cost = 0.0
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if today in line:
                parts = line.strip().split()
                for p in parts:
                    if p.endswith("USD"):
                        try:
                            total_cost += float(p.replace("USD", "").replace(":", ""))
                        except:
                            pass
    msg = f"💸 OpenAI Tageskosten ({today}): {total_cost:.4f} USD"
    send_discord_notification(msg)
    logging.info(msg)

def get_today_openai_cost():
    from datetime import datetime
    log_path = Path("logs/openai_costs.log")
    if not log_path.exists():
        return 0.0
    today = datetime.now().strftime("%Y-%m-%d")
    total_cost = 0.0
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if ",COST," in line and line.startswith(today):
                try:
                    cost = float(line.strip().split(",COST,")[1])
                    total_cost += cost
                except Exception:
                    pass
    return total_cost

def get_total_openai_cost():
    log_path = Path("logs/openai_costs.log")
    if not log_path.exists():
        return 0.0
    total_cost = 0.0
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if ",COST," in line:
                try:
                    cost = float(line.strip().split(",COST,")[1])
                    total_cost += cost
                except Exception:
                    pass
    return total_cost

def main():
    logger.info("🔄 Lade Umgebungsvariablen ...")
    load_dotenv(ENV_PATH)

    # --- Vorherige Werte laden ---
    prev_nennungen, prev_kurse = load_stats(STATS_PATH)

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
        logger.info("🕷️  Starte Reddit-Crawler ...")
        from reddit_crawler import reddit_crawler
        reddit_crawler()
        logger.info("✅ Crawl abgeschlossen")
    except Exception as e:
        logger.error(f"Fehler beim Reddit-Crawl: {e}")

    # --- Ticker-Namensauflösung ---
    try:
        logger.info("📡 Starte Ticker-Namensauflösung ...")
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

    # --- Discord-Benachrichtigung inkl. KI-Zusammenfassung ---
    try:
        import pandas as pd
        from utils import list_pickle_files, load_pickle, load_ticker_names, find_summary_for, load_summary, parse_summary_md
        next_crawl_time = "unbekannt"  # <-- Standardwert setzen!
        timestamp = time.strftime("%d.%m.%Y %H:%M:%S")  # <-- direkt am Anfang!
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

        # Kursdaten für die Top 5 Ticker holen
        top5_ticker = df_ticker["Ticker"].head(5).tolist()
        kurse = get_kurse_parallel(top5_ticker)
        for ticker in top5_ticker:
            df_ticker.loc[df_ticker["Ticker"] == ticker, "Kurs"] = [kurse.get(ticker)]

        # --- KI-Zusammenfassung direkt erzeugen ---
        summary_dict = {}
        for ticker in top5_ticker:
            kursdaten = get_yf_price(ticker)
            news = get_yf_news(ticker)
            context = build_context_with_yahoo(ticker, kursdaten, news)
            summary = summarize_ticker(ticker, context)
            summary_dict[ticker] = summary

        logger.info(f"summary_dict keys: {list(summary_dict.keys())}")

        # OpenAI Kosten für heute abrufen
        openai_cost = get_today_openai_cost()
        openai_cost_total = get_total_openai_cost()

        msg = format_discord_message(
            pickle_name=latest_pickle,
            timestamp=timestamp,
            df_ticker=df_ticker,
            prev_nennungen=prev_nennungen,
            name_map=name_map,
            summary_dict=summary_dict,
            next_crawl_time=next_crawl_time,
            openai_cost=openai_cost,
            openai_cost_total=openai_cost_total
        )

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
            next_crawl_time=next_crawl_time,
            openai_cost=openai_cost,
            openai_cost_total=openai_cost_total
        )
        # Kosten an die Nachricht anhängen
        #msg += f"\n{kosten_str}"

        # Nachricht 1: Crawl-Info, Top 3, Zusammenfassungen, Kosten
        send_discord_notification(msg)
        # Nachricht 2: Legende
        legend = get_discord_legend()
        send_discord_notification(legend)
        # Logging wie gehabt
        logger.info("Discord-Benachrichtigung gesendet!")
        archive_log(LOG_PATH, ARCHIVE_DIR)
    except Exception as e:
        logger.error(f"Fehler bei der Discord-Benachrichtigung: {e} (next_crawl_time: {next_crawl_time if 'next_crawl_time' in locals() else 'unbekannt'})")

    # Am Ende des Tages (z.B. nach dem letzten Crawl):
    if datetime.now().strftime("%H:%M") == "00:00":
        post_daily_openai_cost()

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
            # Suche nach Datum und Uhrzeit im Format: Wochentag YYYY-MM-DD HH:MM:SS
            for i in range(len(parts) - 2):
                if (
                    parts[i].count("-") == 2 and
                    ":" in parts[i + 1]
                ):
                    try:
                        # Beispiel: Wed 2025-07-30 16:00:25
                        dt_str = f"{parts[i]} {parts[i + 1]}"
                        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                        next_time = dt.strftime("%d.%m.%Y %H:%M:%S")
                        return next_time
                    except Exception:
                        continue
            logger.warning(f"Systemd-Timer-Ausgabe unerwartet: {line[0]}")
    except Exception as e:
        logger.warning(f"Fehler beim Auslesen des systemd-Timers: {e}")
    return "unbekannt"

def get_kurse_parallel(ticker_list):
    kurse = {}
    tickers_ohne_kurs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_ticker = {executor.submit(get_yf_price, t): t for t in ticker_list}
        results = {}
        for future in concurrent.futures.as_completed(future_to_ticker):
            t = future_to_ticker[future]
            try:
                results[t] = future.result()
            except Exception as e:
                logger.warning(f"Kursabfrage für {t} fehlgeschlagen: {e}")
                results[t] = None
        for t in ticker_list:
            kurse[t] = results.get(t)
            if not kurse[t] or kurse[t]["regular"] is None:
                tickers_ohne_kurs.append(t)
    if tickers_ohne_kurs:
        logger.warning(f"Keine Kursdaten für folgende Ticker verfügbar: {', '.join(tickers_ohne_kurs)}")
    return kurse

if __name__ == "__main__":
    main()