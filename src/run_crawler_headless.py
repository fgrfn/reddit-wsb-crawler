import os
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from discord_utils import send_discord_notification, format_discord_message
from summarize_ticker import summarize_ticker, build_context_with_yahoo, get_yf_news, extract_text

BASE_DIR = Path(__file__).resolve().parent.parent
os.chdir(BASE_DIR)
# Load environment variables from repo-root/config/.env (preferred) or src/config/.env if not present
env_path = BASE_DIR / "config" / ".env"
if not env_path.exists():
    alt = BASE_DIR / "src" / "config" / ".env"
    if alt.exists():
        env_path = alt
try:
    load_dotenv(dotenv_path=str(env_path))
    logging.info(f"Loaded .env from {env_path}")
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

def get_today_openai_stats():
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
            # Beispielzeile: 2025-07-30T17:23:23.089,COST,0.0020,TOKENS,174,76
            if line.startswith(today) and ",COST," in line and ",TOKENS," in line:
                parts = line.strip().split(",")
                try:
                    cost = float(parts[2])
                    input_tokens = int(parts[4])
                    output_tokens = int(parts[5])
                    total_cost += cost
                    total_input += input_tokens
                    total_output += output_tokens
                except Exception:
                    pass
    return total_cost, total_input, total_output

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

def get_crawl_openai_cost(crawl_ticker_list):
    log_path = Path("logs/openai_costs.log")
    if not log_path.exists():
        return 0.0
    crawl_cost = 0.0
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            # Suche nach Ticker in der Zeile
            for ticker in crawl_ticker_list:
                if f",{ticker}," in line or f" {ticker}:" in line:
                    if ",COST," in line:
                        try:
                            cost = float(line.strip().split(",COST,")[1])
                            crawl_cost += cost
                        except Exception:
                            pass
                    elif ":" in line and "USD" in line:
                        try:
                            cost_part = line.split(":")[1].split("USD")[0].strip()
                            crawl_cost += float(cost_part)
                        except Exception:
                            pass
    return crawl_cost

def get_openai_stats(mode="day", crawl_ticker_list=None):
    from datetime import datetime
    log_path = Path("logs/openai_costs.log")
    if not log_path.exists():
        return 0.0, 0, 0  # Kosten, Input-Tokens, Output-Tokens
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
    logger.info("🔄 Lade Umgebungsvariablen ...")
    load_dotenv(ENV_PATH)

    # --- Crawl-Logfile leeren ---
    with open("logs/openai_costs_crawl.log", "w", encoding="utf-8") as f:
        pass  # Datei leeren

    # --- Tages-Logfile leeren, wenn ein neuer Tag begonnen hat ---
    day_log = "logs/openai_costs_day.log"
    if os.path.exists(day_log):
        mtime = os.path.getmtime(day_log)
        last_mod = datetime.fromtimestamp(mtime)
        if last_mod.date() < datetime.now().date():
            with open(day_log, "w", encoding="utf-8") as f:
                pass  # Datei leeren

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

        # OpenAI Kosten für heute abrufen
        crawl_cost = get_crawl_openai_cost(top5_ticker)
        openai_cost, openai_count, openai_avg = get_today_openai_stats()
        openai_cost_total = get_total_openai_cost()

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
            openai_cost_crawl=crawl_cost,
            openai_tokens_crawl=(crawl_input, crawl_output),
            openai_cost_day=day_cost,
            openai_tokens_day=(day_input, day_output),
            openai_cost_total=total_cost,
            openai_tokens_total=(total_input, total_output)
        )
        # Kosten an die Nachricht anhängen
        #msg += f"\n{kosten_str}"

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
