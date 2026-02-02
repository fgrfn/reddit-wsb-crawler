import os
import sys
import time
import pickle
import subprocess
import logging
import yfinance as yf
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from __version__ import __version__

# Ensure imports of local modules work regardless of CWD
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(REPO_ROOT))

from discord_utils import send_discord_notification, format_discord_message, send_or_edit_discord_message, format_heartbeat_message
from summarize_ticker import summarize_ticker, build_context_with_yahoo, get_yf_news, extract_text

BASE_DIR = REPO_ROOT
os.chdir(BASE_DIR)

# Load environment variables from repo-root/config/.env (preferred) or src/config/.env if present
env_path = BASE_DIR / "config" / ".env"
if not env_path.exists():
    alt = BASE_DIR / "src" / "config" / ".env"
    if alt.exists():
        env_path = alt
ENV_PATH = str(env_path) if env_path.exists() else None
try:
    if ENV_PATH:
        load_dotenv(dotenv_path=ENV_PATH)
        logging.info(f"Loaded .env from {ENV_PATH}")
    else:
        load_dotenv()  # fallback: default behaviour (env or .env in CWD)
        logging.info("No explicit config/.env found — loaded defaults if present")
except Exception:
    logging.warning("No .env loaded (config/.env not found)")

LOG_PATH = BASE_DIR / "logs" / "crawler.log"
ARCHIVE_DIR = BASE_DIR / "logs" / "archive"
SYMBOLS_PKL = BASE_DIR / "data" / "input" / "symbols_list.pkl"
NAME_RESOLVER_SCRIPT = BASE_DIR / "src" / "build_ticker_name_cache.py"
PICKLE_DIR = BASE_DIR / "data" / "output" / "pickle"
SUMMARY_DIR = BASE_DIR / "data" / "output" / "summaries"
TICKER_NAME_PATH = BASE_DIR / "data" / "input" / "ticker_name_map.pkl"
STATS_PATH = BASE_DIR / "data" / "output" / "ticker_stats.pkl"  # <--- NEU
HEARTBEAT_STATE_PATH = BASE_DIR / "data" / "state" / "heartbeat.json"  # <--- Heartbeat Message-ID

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# Custom handler that forces flush after every log
class FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

# Configure logging with unbuffered output for Docker
file_handler = FlushFileHandler(LOG_PATH, encoding="utf-8", delay=False)
file_handler.setLevel(logging.INFO)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[file_handler, stream_handler],
    force=True  # Override any existing config
)
logger = logging.getLogger(__name__)

def archive_log(log_path: Path, archive_dir: Path) -> None:
    """Archiviert Logfile mit Zeitstempel."""
    import shutil
    from datetime import datetime
    if not log_path.exists():
        return
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_file = archive_dir / f"{log_path.stem}_{ts}.log"
    shutil.copy(str(log_path), str(archive_file))
    logger.info(f"Logfile archiviert: {archive_file}")

def get_yf_price(symbol: str) -> dict:
    """Holt Kursdaten für ein Symbol von Yahoo Finance.
    
    Returns:
        dict mit Keys: regular, pre, post, previousClose, change, changePercent, currency, timestamp
    """
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

def save_stats(stats_path: Path, nennungen_dict: dict, kurs_dict: dict) -> None:
    """Speichert Ticker-Statistiken (Nennungen und Kurse) als Pickle."""
    with open(stats_path, "wb") as f:
        pickle.dump({"nennungen": nennungen_dict, "kurs": kurs_dict}, f)

def load_stats(stats_path: Path) -> tuple[dict, dict]:
    """Lädt gespeicherte Ticker-Statistiken.
    
    Returns:
        tuple: (nennungen_dict, kurs_dict)
    """
    if not os.path.exists(stats_path):
        return {}, {}
    with open(stats_path, "rb") as f:
        data = pickle.load(f)
        return data.get("nennungen", {}), data.get("kurs", {})


def check_triggers(aktuelle_nennungen, stats_path=STATS_PATH, alert_ratio=2.0, alert_min_delta=10, alert_min_abs=20):
    """Prüft, welche Ticker die Alert-Kriterien erfüllen.

    Returns: list of tuples (ticker, prev, curr, delta)
    """
    try:
        baseline_prev_nennungen, _ = load_stats(stats_path)
    except Exception:
        baseline_prev_nennungen = {}

    triggered = []
    for ticker, curr in aktuelle_nennungen.items():
        try:
            curr_i = int(curr)
        except Exception:
            continue
        prev = int(baseline_prev_nennungen.get(ticker, 0))
        delta = curr_i - prev
        if prev == 0:
            if curr_i >= alert_min_abs:
                triggered.append((ticker, prev, curr_i, delta))
        else:
            if delta >= alert_min_delta and curr_i >= prev * alert_ratio:
                triggered.append((ticker, prev, curr_i, delta))
    return triggered

def get_openai_stats(mode="day", crawl_ticker_list=None):
    """Ermittelt OpenAI API Kosten und Token-Nutzung.
    
    Args:
        mode: "day" für heutige Stats, "crawl" für spezifische Ticker, "total" für Gesamtkosten
        crawl_ticker_list: Liste von Ticker-Symbolen (nur bei mode="crawl")
    
    Returns:
        tuple: (kosten, input_tokens, output_tokens)
    """
    from datetime import datetime
    log_path = Path("logs/openai_costs.log")
    if not log_path.exists():
        return 0.0, 0, 0
    today = datetime.now().strftime("%Y-%m-%d")
    total_cost = 0.0
    total_input = 0
    total_output = 0
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if ",COST," in line and ",TOKENS," in line:
                parts = line.strip().split(",")
                date_part = parts[0]
                cost = float(parts[2])
                input_tokens = int(parts[4])
                output_tokens = int(parts[5])
                ticker_in_log = parts[6] if len(parts) > 6 else None
                if mode == "day" and date_part.startswith(today):
                    total_cost += cost
                    total_input += input_tokens
                    total_output += output_tokens
                elif mode == "crawl" and crawl_ticker_list and ticker_in_log:
                    if ticker_in_log in crawl_ticker_list:
                        total_cost += cost
                        total_input += input_tokens
                        total_output += output_tokens
                elif mode == "total":
                    total_cost += cost
                    total_input += input_tokens
                    total_output += output_tokens
    return total_cost, total_input, total_output

def get_openai_stats_from_file(log_path):
    if not Path(log_path).exists():
        return 0.0, 0, 0
    total_cost = 0.0
    total_input = 0
    total_output = 0
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if ",COST," in line and ",TOKENS," in line:
                parts = line.strip().split(",")
                cost = float(parts[2])
                input_tokens = int(parts[4])
                output_tokens = int(parts[5])
                total_cost += cost
                total_input += input_tokens
                total_output += output_tokens
    return total_cost, total_input, total_output

def main():
    logger.info(f"🚀 WSB-Crawler v{__version__} gestartet")
    logger.info("🔄 Lade Umgebungsvariablen ...")
    load_dotenv(ENV_PATH)

    # --- Crawl-Logfile leeren ---
    crawl_log_path = BASE_DIR / "logs" / "openai_costs_crawl.log"
    crawl_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(crawl_log_path, "w", encoding="utf-8") as f:
        f.write(f"# OpenAI Costs - Crawl gestartet: {datetime.now()}\n")
        f.flush()  # Force write to disk

    # --- Tages-Logfile leeren, wenn ein neuer Tag begonnen hat ---
    day_log = BASE_DIR / "logs" / "openai_costs_day.log"
    day_log.parent.mkdir(parents=True, exist_ok=True)
    if day_log.exists():
        mtime = day_log.stat().st_mtime
        last_mod = datetime.fromtimestamp(mtime)
        if last_mod.date() < datetime.now().date():
            with open(day_log, "w", encoding="utf-8") as f:
                f.write(f"# OpenAI Costs - Tag: {datetime.now().date()}\n")
                f.flush()  # Force write to disk
    else:
        with open(day_log, "w", encoding="utf-8") as f:
            f.write(f"# OpenAI Costs - Tag: {datetime.now().date()}\n")
            f.flush()

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
            capture_output=True, text=True, timeout=60
        )
        logger.info(result.stdout)
        if result.stderr:
            logger.warning(f"Resolver stderr: {result.stderr}")
        if result.returncode == 0:
            logger.info("Namensauflösung abgeschlossen!")
        else:
            logger.error(f"Fehler bei der Namensauflösung. Return code: {result.returncode}")
            logger.error(f"Resolver stderr: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("Namensauflösung timeout nach 60 Sekunden.")
    except Exception as e:
        logger.error(f"Fehler beim Resolver: {e}", exc_info=True)

    # --- Discord-Benachrichtigung inkl. KI-Zusammenfassung ---
    try:
        import pandas as pd
        from utils import list_pickle_files, load_pickle, load_ticker_names, find_summary_for, load_summary, parse_summary_md
        timestamp = time.strftime("%d.%m.%Y %H:%M:%S")
        next_crawl_time = get_next_systemd_run()
        pickle_files = list_pickle_files(PICKLE_DIR)
        if not pickle_files:
            logger.warning("Keine Pickle-Datei gefunden, keine Benachrichtigung möglich.")
            return
        latest_pickle = sorted(pickle_files)[-1]
        result = load_pickle(PICKLE_DIR / latest_pickle)
        name_map = load_ticker_names(TICKER_NAME_PATH)
        df_rows = []
        for subreddit, srdata in result.get("subreddits", {}).items():
            for symbol, count in srdata.get("symbol_hits", {}).items():
                df_rows.append({
                    "Ticker": symbol,
                    "Subreddit": subreddit,
                    "Nennungen": count,
                    "Kurs": None,  # Kurse werden später separat geladen
                })
        df = pd.DataFrame(df_rows)
        df["Unternehmen"] = df["Ticker"].map(name_map)
        df_ticker = (
            df.groupby(["Ticker", "Unternehmen"], as_index=False)["Nennungen"]
            .sum()
            .sort_values(by="Nennungen", ascending=False)
        )
        # Initialize Kurs column with None
        df_ticker["Kurs"] = None
        
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
            # Build context including Yahoo data, news and snippets from Reddit picks
            context = build_context_with_yahoo(ticker, kursdaten, news)
            try:
                reddit_ctx = extract_text(result, ticker)
            except Exception:
                reddit_ctx = ""
            if reddit_ctx:
                context = context + "\n\nReddit-Diskussion:\n" + reddit_ctx
            summary = summarize_ticker(ticker, context)
            summary_dict[ticker] = summary

        logger.info(f"summary_dict keys: {list(summary_dict.keys())}")

        # OpenAI Kosten für heute abrufen (aus separaten Log-Dateien)
        crawl_cost, crawl_input, crawl_output = get_openai_stats_from_file("logs/openai_costs_crawl.log")
        day_cost, day_input, day_output = get_openai_stats_from_file("logs/openai_costs_day.log")
        total_cost, total_input, total_output = get_openai_stats_from_file("logs/openai_costs_total.log")

        msg = format_discord_message(
            pickle_name=latest_pickle,
            timestamp=timestamp,
            df_ticker=df_ticker,
            prev_nennungen=prev_nennungen,
            name_map=name_map,
            summary_dict=summary_dict,
            next_crawl_time=next_crawl_time,
            openai_cost_crawl=crawl_cost,
            openai_tokens_crawl=(crawl_input, crawl_output),
            openai_cost_day=day_cost,
            openai_tokens_day=(day_input, day_output),
            openai_cost_total=total_cost,
            openai_tokens_total=(total_input, total_output)
        )

        # Nach dem Erstellen von df_ticker:
        aktuelle_nennungen = dict(zip(df_ticker["Ticker"], df_ticker["Nennungen"]))
        # Handle None values in Kurs column - only include valid price data
        try:
            aktuelle_kurse = {}
            for ticker, kurs in zip(df_ticker["Ticker"], df_ticker["Kurs"]):
                if kurs is not None and isinstance(kurs, dict):
                    aktuelle_kurse[ticker] = kurs
        except KeyError:
            # If Kurs column doesn't exist, use empty dict
            logger.warning("Kurs-Spalte nicht gefunden in df_ticker, verwende leeres Dictionary.")
            aktuelle_kurse = {}
        save_stats(STATS_PATH, aktuelle_nennungen, aktuelle_kurse)


        msg = format_discord_message(
            pickle_name=latest_pickle,
            timestamp=timestamp,
            df_ticker=df_ticker,
            prev_nennungen=prev_nennungen,
            name_map=name_map,
            summary_dict=summary_dict,
            next_crawl_time=next_crawl_time,
            openai_cost_crawl=crawl_cost,
            openai_tokens_crawl=(crawl_input, crawl_output),
            openai_cost_day=day_cost,
            openai_tokens_day=(day_input, day_output),
            openai_cost_total=total_cost,
            openai_tokens_total=(total_input, total_output)
        )


        # Nur bei signifikantem Anstieg Benachrichtigung senden
        ALERT_RATIO = float(os.getenv("ALERT_RATIO", "2.0"))
        ALERT_MIN_DELTA = int(os.getenv("ALERT_MIN_DELTA", "10"))
        ALERT_MIN_ABS = int(os.getenv("ALERT_MIN_ABS", "20"))

        triggered = check_triggers(
            aktuelle_nennungen,
            stats_path=STATS_PATH,
            alert_ratio=ALERT_RATIO,
            alert_min_delta=ALERT_MIN_DELTA,
            alert_min_abs=ALERT_MIN_ABS,
        )

        if triggered:
            tickers_str = ", ".join([t[0] for t in triggered])
            logger.info(f"Signifikante Erhöhungen entdeckt: {tickers_str} — sende Discord-Benachrichtigung.")
            # Nur Top-1 Ticker in der Benachrichtigung zeigen
            df_top1 = df_ticker.head(1).copy()
            msg_top1 = format_discord_message(
                pickle_name=latest_pickle,
                timestamp=timestamp,
                df_ticker=df_top1,
                prev_nennungen=prev_nennungen,
                name_map=name_map,
                summary_dict=summary_dict,
                next_crawl_time=next_crawl_time,
                openai_cost_crawl=crawl_cost,
                openai_tokens_crawl=(crawl_input, crawl_output),
                openai_cost_day=day_cost,
                openai_tokens_day=(day_input, day_output),
                openai_cost_total=total_cost,
                openai_tokens_total=(total_input, total_output)
            )
            # Nur die Top-1 Nachricht senden (Legende weggelassen)
            send_discord_notification(msg_top1)
            logger.info("Discord-Benachrichtigung gesendet!")
        else:
            logger.info("Keine signifikanten Nennungsanstiege — Discord-Benachrichtigung übersprungen.")
        
        # Status-Nachricht editieren (kein Ping, nur stille Aktualisierung)
        status_update = os.getenv("DISCORD_STATUS_UPDATE", "true").lower() in ("true", "1", "yes")
        if status_update:
            try:
                import json
                top_tickers_list = [(row["Ticker"], row["Nennungen"]) for _, row in df_ticker.head(5).iterrows()]
                status_msg = format_heartbeat_message(
                    timestamp=timestamp,
                    run_id=result.get("run_id", "unknown"),
                    total_posts=result.get("total_posts", 0),
                    top_tickers=top_tickers_list,
                    next_crawl_time=next_crawl_time,
                    triggered_count=len(triggered)
                )
                
                # Lade gespeicherte Message-ID
                status_id = None
                if HEARTBEAT_STATE_PATH.exists():
                    try:
                        with open(HEARTBEAT_STATE_PATH, "r", encoding="utf-8") as f:
                            state = json.load(f)
                            status_id = state.get("message_id")
                    except Exception:
                        pass
                
                result_status = send_or_edit_discord_message(status_msg, message_id=status_id)
                
                if result_status and result_status.get("success"):
                    # Speichere neue Message-ID
                    new_id = result_status.get("message_id")
                    if new_id:
                        HEARTBEAT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                        with open(HEARTBEAT_STATE_PATH, "w", encoding="utf-8") as f:
                            json.dump({"message_id": new_id, "last_update": timestamp}, f)
                    logger.info(f"Status-Nachricht {'editiert' if status_id else 'erstellt'} (kein Ping).")
            except Exception as e:
                logger.warning(f"Fehler beim Aktualisieren der Status-Nachricht: {e}")

        archive_log(LOG_PATH, ARCHIVE_DIR)
    except Exception as e:
        logger.error(f"Fehler bei der Discord-Benachrichtigung: {e} (next_crawl_time: {next_crawl_time if 'next_crawl_time' in locals() else 'unbekannt'})")



def get_next_systemd_run(timer_name: str = "reddit_crawler.timer") -> str:
    """Ermittelt die nächste geplante Timer-Ausführung via systemctl.
    
    Returns:
        str: Formatierter Zeitstempel oder "unbekannt"
    """
    # In Docker-Containern ist systemctl nicht verfügbar
    import shutil
    if not shutil.which("systemctl"):
        return "unbekannt (Docker)"
    
    try:
        result = subprocess.run(
            ["systemctl", "list-timers", timer_name, "--no-legend", "--all"],
            capture_output=True, text=True
        )
        line = result.stdout.strip().splitlines()
        if line:
            # Die erste Spalte ist der nächste geplante Start (NEXT)
            parts = line[0].split()
            # parts[0] = NEXT (Datum+Uhrzeit)
            if len(parts) >= 1:
                # Format: YYYY-MM-DD HH:MM:SS
                dt_str = parts[0] + " " + parts[1] if len(parts) > 1 else parts[0]
                try:
                    # systemd gibt oft "YYYY-MM-DD HH:MM:SS" zurück
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    return dt.strftime("%d.%m.%Y %H:%M:%S")
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Fehler beim Auslesen des systemd-Timers: {e}")
    return "unbekannt"

def get_kurse_parallel(ticker_list: list[str]) -> dict:
    """Holt Kursdaten parallel für mehrere Ticker.
    
    Returns:
        dict: {ticker: kurs_data}
    """
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
