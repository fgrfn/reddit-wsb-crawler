import os
import sys
import subprocess
import threading
import time
import datetime
import json
import glob
import psutil
import pandas as pd
import schedule
from PIL import Image
import streamlit as st
from pathlib import Path

from reddit_crawler import reddit_crawler
from utils import (
    update_dotenv_variable,
    list_pickle_files,
    list_summary_files,
    find_summary_for,
    load_pickle,
    load_summary,
    parse_summary_md,
    load_ticker_names
)
from log_utils import archive_log
from discord_utils import send_discord_notification, format_discord_message
import summarizer

BASE_DIR = Path(__file__).resolve().parent.parent
PICKLE_DIR = BASE_DIR / "data" / "output" / "pickle"
SUMMARY_DIR = BASE_DIR / "data" / "output" / "summaries"
CHART_DIR = BASE_DIR / "data" / "output" / "charts"
EXCEL_PATH = BASE_DIR / "data" / "output" / "excel" / "ticker_sentiment_summary.xlsx"
LOG_PATH = BASE_DIR / "logs" / "crawler.log"
ARCHIVE_DIR = LOG_PATH.parent / "archive"
ENV_PATH = BASE_DIR / "config" / ".env"
TICKER_NAME_PATH = BASE_DIR / "data" / "input" / "ticker_name_map.pkl"
name_map = load_ticker_names(TICKER_NAME_PATH)
SCHEDULE_CONFIG_PATH = BASE_DIR / "config" / "schedule.json"

CRAWL_FLAG = "crawl_running.flag"

def set_crawl_flag():
    with open(CRAWL_FLAG, "w") as f:
        f.write("running")

def clear_crawl_flag():
    import logging
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Versuche crawl_running.flag zu löschen: {os.path.abspath(CRAWL_FLAG)}")
    if os.path.exists(CRAWL_FLAG):
        try:
            os.remove(CRAWL_FLAG)
            logging.info("crawl_running.flag erfolgreich gelöscht.")
        except Exception as e:
            logging.error(f"Fehler beim Löschen von crawl_running.flag: {e}")
    else:
        logging.info("crawl_running.flag existiert nicht.")

def is_crawl_running():
    return os.path.exists(CRAWL_FLAG)

def save_schedule_config(interval_type, interval_value, crawl_time):
    now = datetime.datetime.now()
    if interval_type == "Täglich" and crawl_time:
        next_run = now.replace(hour=crawl_time.hour, minute=crawl_time.minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += datetime.timedelta(days=1)
    elif interval_type == "Stündlich":
        next_run = now + datetime.timedelta(hours=interval_value)
    elif interval_type == "Minütlich":
        next_run = now + datetime.timedelta(minutes=interval_value)
    else:
        next_run = None

    config = {
        "interval_type": interval_type,
        "interval_value": interval_value,
        "crawl_time": crawl_time.strftime("%H:%M") if crawl_time else None,
        "next_run": next_run.isoformat() if next_run else None
    }
    SCHEDULE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f)

def load_schedule_config():
    if not SCHEDULE_CONFIG_PATH.exists():
        return None
    with open(SCHEDULE_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    # Prüfe, ob next_run in der Vergangenheit liegt
    if config.get("next_run"):
        next_run = datetime.datetime.fromisoformat(config["next_run"])
        now = datetime.datetime.now()
        while next_run <= now:
            if config["interval_type"] == "Täglich" and config.get("crawl_time"):
                next_run += datetime.timedelta(days=1)
            elif config["interval_type"] == "Stündlich":
                next_run += datetime.timedelta(hours=config["interval_value"])
            elif config["interval_type"] == "Minütlich":
                next_run += datetime.timedelta(minutes=config["interval_value"])
            else:
                break
        config["next_run"] = next_run.isoformat()
        # Optional: Schreibe die aktualisierte Zeit zurück
        with open(SCHEDULE_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f)
    return config

def start_crawler_and_wait():
    global name_map

    # Logfile archivieren, bevor ein neuer Crawl startet
    for _ in range(5):
        try:
            archive_log(LOG_PATH, ARCHIVE_DIR)
            break
        except PermissionError:
            time.sleep(0.5)
    else:
        st.error("Konnte Logfile nicht archivieren (noch gesperrt).")

    if st.session_state.get("crawl_running", False):
        log_event("Crawler läuft bereits.", "WARNING", True)
        return

    st.session_state["crawl_running"] = True
    set_crawl_flag()
    log_event("🕷️ Crawl gestartet ...", "INFO", True)

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("🕷️ Crawl gestartet ...\n")

        with open(LOG_PATH, "a", encoding="utf-8") as log_handle:
            crawler_proc = subprocess.Popen(
                [sys.executable, os.path.join("src", "main_crawler.py")],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
                cwd=str(BASE_DIR),
                close_fds=True
            )
            st.session_state["crawler_pid"] = crawler_proc.pid
        log_event(f"Crawler-Prozess gestartet (PID: {crawler_proc.pid})", "INFO", True)

        status = st.status("🕷️ Crawler läuft ...", expanded=True)
        with st.expander("📜 Crawl-Log anzeigen", expanded=True):
            log_view = st.empty()
            log_content = ""
            existing = set(list_pickle_files(PICKLE_DIR))
            timeout = 300
            start_time = time.time()
            new_pickle = None
            while time.time() - start_time < timeout:
                if LOG_PATH.exists():
                    try:
                        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                            log_content = f.read()
                    except Exception:
                        log_content = ""
                    log_view.code(log_content, language="bash", height=400)
                    st.session_state["last_log"] = log_content

                current = set(list_pickle_files(PICKLE_DIR))
                diff = current - existing
                if diff:
                    new_pickle = sorted(diff)[0]
                    status.update(label="✅ Crawl abgeschlossen", state="complete")
                    st.success(f"Neue Analyse geladen: `{new_pickle}`")
                    crawler_proc.wait()
                    time.sleep(0.5)
                    break

                if crawler_proc.poll() is not None:
                    if not new_pickle and current:
                        new_pickle = sorted(current)[-1]
                    break

                time.sleep(2)
            else:
                status.update(label="⚠️ Timeout – keine neue Datei gefunden", state="error")
                st.warning("Der Crawler hat keine neue Analyse erzeugt – benutze letzte vorhandene Datei für Discord.")
                pickle_files = list_pickle_files(PICKLE_DIR)
                if not pickle_files:
                    st.error("Keine Pickle-Datei gefunden, keine Benachrichtigung möglich.")
                    return
                new_pickle = sorted(pickle_files)[-1]

            # --- Discord-Benachrichtigung immer senden, auch wenn keine neue Datei ---
            try:
                if not new_pickle:
                    pickle_files = list_pickle_files(PICKLE_DIR)
                    if not pickle_files:
                        st.error("Keine Pickle-Datei gefunden.")
                        return
                    new_pickle = sorted(pickle_files)[-1]

                result = load_pickle(PICKLE_DIR / new_pickle)
                df_rows = []
                for subreddit, srdata in result.get("subreddits", {}).items():
                    for symbol, count in srdata["symbol_hits"].items():
                        df_rows.append({"Ticker": symbol, "Subreddit": subreddit, "Nennungen": count})
                df = pd.DataFrame(df_rows)
                top3 = (
                    df.groupby("Ticker")["Nennungen"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(3)
                    .index.tolist()
                )

                # --- KI-Zusammenfassung für die Top 3 immer erzeugen ---
                print(f"Automatische Zusammenfassung: top3={top3}, new_pickle={new_pickle}")
                if not top3:
                    print("Warnung: top3 ist leer, Zusammenfassung für alle Ticker wird erzeugt.")
                    summarizer.generate_summary(
                        pickle_path=PICKLE_DIR / new_pickle,
                        include_all=True,
                        streamlit_out=None,
                        only_symbols=None
                    )
                else:
                    summarizer.generate_summary(
                        pickle_path=PICKLE_DIR / new_pickle,
                        include_all=False,
                        streamlit_out=None,
                        only_symbols=top3
                    )
                with open(LOG_PATH, "a", encoding="utf-8") as log_handle:
                    log_handle.write("✅ KI-Zusammenfassung abgeschlossen.\n")
                st.success("✅ KI-Zusammenfassung abgeschlossen.")
            except Exception as e:
                with open(LOG_PATH, "a", encoding="utf-8") as log_handle:
                    log_handle.write(f"❌ KI-Zusammenfassung fehlgeschlagen: {e}\n")
                st.error(f"❌ KI-Zusammenfassung fehlgeschlagen: {e}")

            # Discord-Benachrichtigung nach dem Crawl senden (optimiertes Format)
            try:
                pickle_files = list_pickle_files(PICKLE_DIR)
                if pickle_files:
                    latest_pickle = sorted(pickle_files)[-1]
                    result = load_pickle(PICKLE_DIR / latest_pickle)
                    df_rows = []
                    for subreddit, srdata in result.get("subreddits", {}).items():
                        for symbol, count in srdata["symbol_hits"].items():
                            df_rows.append({
                                "Ticker": symbol,
                                "Subreddit": subreddit,
                                "Nennungen": count,
                                "Kurs": srdata.get("price", {}).get(symbol),  # falls vorhanden
                            })
                    df = pd.DataFrame(df_rows)
                    df["Unternehmen"] = df["Ticker"].map(name_map)
                    df_ticker = (
                        df.groupby(["Ticker", "Unternehmen"], as_index=False)["Nennungen"]
                        .sum()
                        .sort_values(by="Nennungen", ascending=False)
                    )
                    # Trend-Berechnung
                    pickle_files = sorted(list_pickle_files(PICKLE_DIR))
                    if len(pickle_files) >= 2:
                        prev_pickle = pickle_files[-2]
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
                    if not summary_path or not summary_path.exists():
                        run_id = latest_pickle.split("_")[0]
                        possible_path = SUMMARY_DIR / f"{run_id}_summary.md"
                        if possible_path.exists():
                            summary_path = possible_path

                    summary_dict = {}
                    if summary_path and summary_path.exists():
                        summary_text = load_summary(summary_path)
                        summary_dict = parse_summary_md(summary_text)

                    timestamp = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                    msg = format_discord_message(
                        pickle_name=latest_pickle,
                        timestamp=timestamp,
                        df_ticker=df_ticker,
                        prev_nennungen=prev_nennungen,
                        name_map=name_map,
                        summary_dict=summary_dict
                    )

                    print("DEBUG: Bereite Discord-Nachricht vor...")
                    if len(msg) > 2000:
                        print("WARNUNG: Discord-Nachricht zu lang, wird gekürzt!")
                        msg = msg[:1997] + "..."

                    success = send_discord_notification(msg)
                    print(f"DEBUG: Discord-Nachricht gesendet? {success}")
                    if success:
                        st.success("Discord-Benachrichtigung gesendet!")
                        st.rerun()
                    else:
                        st.error("Fehler beim Senden der Discord-Benachrichtigung.")
                else:
                    st.error("Keine Pickle-Datei gefunden, keine Benachrichtigung möglich.")
            except Exception as e:
                st.error(f"Fehler beim Senden der Discord-Benachrichtigung: {e}")

            # Status erst jetzt zurücksetzen!
            st.session_state.pop("crawler_pid", None)
            st.session_state["crawl_running"] = False
            clear_crawl_flag()
            # Nach jedem Crawl: Namensauflösung automatisch ausführen
            subprocess.run(
                [sys.executable, os.path.join("src", "build_ticker_name_cache.py")],
                capture_output=True, text=True
            )

            name_map = load_ticker_names(TICKER_NAME_PATH)

            # Discord-Benachrichtigung nach dem Crawl senden (optimiertes Format)
            try:
                pickle_files = list_pickle_files(PICKLE_DIR)
                if pickle_files:
                    latest_pickle = sorted(pickle_files)[-1]
                    result = load_pickle(PICKLE_DIR / latest_pickle)
                    df_rows = []
                    for subreddit, srdata in result.get("subreddits", {}).items():
                        for symbol, count in srdata["symbol_hits"].items():
                            df_rows.append({
                                "Ticker": symbol,
                                "Subreddit": subreddit,
                                "Nennungen": count,
                                "Kurs": srdata.get("price", {}).get(symbol),  # falls vorhanden
                            })
                    df = pd.DataFrame(df_rows)
                    df["Unternehmen"] = df["Ticker"].map(name_map)
                    df_ticker = (
                        df.groupby(["Ticker", "Unternehmen"], as_index=False)["Nennungen"]
                        .sum()
                        .sort_values(by="Nennungen", ascending=False)
                    )
                    # Trend-Berechnung
                    pickle_files = sorted(list_pickle_files(PICKLE_DIR))
                    if len(pickle_files) >= 2:
                        prev_pickle = pickle_files[-2]
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
                    if not summary_path or not summary_path.exists():
                        run_id = latest_pickle.split("_")[0]
                        possible_path = SUMMARY_DIR / f"{run_id}_summary.md"
                        if possible_path.exists():
                            summary_path = possible_path

                    summary_dict = {}
                    if summary_path and summary_path.exists():
                        summary_text = load_summary(summary_path)
                        summary_dict = parse_summary_md(summary_text)

                    timestamp = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                    msg = format_discord_message(
                        pickle_name=latest_pickle,
                        timestamp=timestamp,
                        df_ticker=df_ticker,
                        prev_nennungen=prev_nennungen,
                        name_map=name_map,
                        summary_dict=summary_dict
                    )

                    print("DEBUG: Bereite Discord-Nachricht vor...")
                    if len(msg) > 2000:
                        print("WARNUNG: Discord-Nachricht zu lang, wird gekürzt!")
                        msg = msg[:1997] + "..."

                    success = send_discord_notification(msg)
                    print(f"DEBUG: Discord-Nachricht gesendet? {success}")
                    if success:
                        st.success("Discord-Benachrichtigung gesendet!")
                    else:
                        st.error("Fehler beim Senden der Discord-Benachrichtigung.")
            except Exception as e:
                st.error(f"Fehler beim Senden der Discord-Benachrichtigung: {e}")
    finally:
        clear_crawl_flag()

def stop_crawler():
    import psutil
    pid = st.session_state.get("crawler_pid")
    if pid:
        try:
            p = psutil.Process(pid)
            st.info(f"Prozess-Status vor Stop: {p.status()}")
            p.terminate()
            try:
                p.wait(timeout=5)
            except psutil.TimeoutExpired:
                os.system(f"kill -9 {pid}")
            st.success("Crawl-Prozess wurde gestoppt.")
        except Exception as e:
            st.error(f"Fehler beim Stoppen des Prozesses: {e}")
        st.session_state["crawl_running"] = False
        st.session_state.pop("crawler_pid", None)
        clear_crawl_flag()
        st.rerun()

def run_resolver_ui():
    st.header("📡 Ticker-Namen auflösen")

    ticker_input = st.text_area("🔣 Ticker eingeben (kommagetrennt)", "TSLA, AAPL, BLTN, XYZ123")
    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]

    if st.button("🚀 Auflösen"):
        if not tickers:
            st.warning("Bitte gib mindestens ein Ticker-Symbol ein.")
            return

        progress = st.progress(0)
        status = st.empty()
        results = {}
        total = len(tickers)

        # Fortschritts-Wrapper
        def update_progress(i, sym):
            pct = int((i + 1) / total * 100)
            progress.progress(pct, text=f"{sym} ({i + 1}/{total})")
            status.info(f"Aktuell: {sym}")

        from time import sleep  # nur für Demo-Zwecke

        # Entferne diese Zeilen:
        # st.subheader("📋 Ergebnis:")
        # st.table({k: v or "❌ Nicht gefunden" for k, v in results.items()}.items())
        # import pandas as pd
        # df = pd.DataFrame(list(results.items()), columns=["Symbol", "Firmenname"])
        # csv = df.to_csv(index=False).encode("utf-8")
        # st.download_button("⬇️ Als CSV herunterladen", csv, "ticker_results.csv", "text/csv")

scheduler_thread = None
scheduler_stop_event = threading.Event()

def run_scheduled_crawler(interval_type, interval_value, crawl_time=None):
    def job():
        start_crawler_and_wait()

    schedule.clear()
    if interval_type == "Täglich" and crawl_time:
        schedule.every().day.at(crawl_time.strftime("%H:%M")).do(job)
    elif interval_type == "Stündlich":
        schedule.every(interval_value).hours.do(job)
    elif interval_type == "Minütlich":
        schedule.every(interval_value).minutes.do(job)

    while not scheduler_stop_event.is_set():
        schedule.run_pending()
        time.sleep(10)

def start_scheduler(interval_type, interval_value, crawl_time=None):
    global scheduler_thread, scheduler_stop_event
    if scheduler_thread and scheduler_thread.is_alive():
        st.warning("Zeitplaner läuft bereits.")
        return
    scheduler_stop_event.clear()
    scheduler_thread = threading.Thread(
        target=run_scheduled_crawler,
        args=(interval_type, interval_value, crawl_time),
        daemon=True
    )
    scheduler_thread.start()
    st.success("Zeitplaner gestartet.")

def get_schedule_description():
    jobs = schedule.get_jobs()
    if not jobs:
        return "Kein Zeitplan aktiv."
    descs = []
    for job in jobs:
        next_run = job.next_run.strftime("%d.%m.%Y %H:%M:%S") if job.next_run else "unbekannt"
        if job.unit == "days":
            descs.append(f"Täglich um {job.at_time.strftime('%H:%M')} (nächster Lauf: {next_run})")
        elif job.unit == "hours":
            descs.append(f"Alle {job.interval} Stunde(n) (nächster Lauf: {next_run})")
        elif job.unit == "minutes":
            descs.append(f"Alle {job.interval} Minute(n) (nächster Lauf: {next_run})")
        else:
            descs.append(f"{str(job)} (nächster Lauf: {next_run})")
    return "\n".join(descs)

def clear_schedule():
    global scheduler_thread, scheduler_stop_event
    schedule.clear()
    scheduler_stop_event.set()
    scheduler_thread = None
    # Konfigurationsdatei löschen
    if SCHEDULE_CONFIG_PATH.exists():
        SCHEDULE_CONFIG_PATH.unlink()
    # Session-Flag entfernen
    st.session_state.pop("scheduler_started", None)

import glob

def find_log_for_pickle(pickle_filename):
    # Extrahiere Zeitstempel aus Pickle-Dateiname
    ts = pickle_filename.split("_")[0]
    # Suche nach Logfile mit gleichem Zeitstempel im Archiv
    pattern = str(ARCHIVE_DIR / f"{ts}_*.log")
    matches = glob.glob(pattern)
    return matches[0] if matches else None

def log_event(message, level="INFO", show_in_ui=False):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}\n"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"Fehler beim Schreiben ins Log: {e}")
    if show_in_ui:
        if level == "ERROR":
            st.error(message)
        elif level == "WARNING":
            st.warning(message)
        elif level == "SUCCESS":
            st.success(message)
        else:
            st.info(message)

def main():
    st.set_page_config(page_title="Reddit Crawler Dashboard", layout="wide")
    st.title("🕷️ Reddit Crawler Dashboard")

    # --- Automatischer Reset, falls Flag fehlt ---
    if not is_crawl_running() and st.session_state.get("crawl_running", False):
        st.session_state["crawl_running"] = False
        st.session_state.pop("crawler_pid", None)

    config = load_schedule_config()
    # Zeitplan nach Neustart wiederherstellen
    if config and not st.session_state.get("scheduler_started"):
        interval_type = config.get("interval_type")
        interval_value = config.get("interval_value")
        crawl_time = None
        if config.get("crawl_time"):
            crawl_time = datetime.datetime.strptime(config["crawl_time"], "%H:%M").time()
        start_scheduler(interval_type, interval_value, crawl_time)
        st.session_state["scheduler_started"] = True
    elif not config:
        schedule.clear()
        st.session_state.pop("scheduler_started", None)

    if st.session_state.get("crawl_running", False):
        st.info("🟡 Ein Crawl läuft gerade (manuell oder automatisch)...")
        if st.sidebar.button("🛑 Crawl stoppen"):
            stop_crawler()
            st.stop()

    col_dashboard, col_settings = st.columns([3, 1])

    with col_settings:
        with st.expander("🕒 Zeitplanung", expanded=True):
            st.markdown("Hier kannst du den automatischen Start des Crawlers planen.")

            if config and config.get("next_run"):
                next_run = datetime.datetime.fromisoformat(config["next_run"])
                st.info(f"Nächster Crawl: {next_run.strftime('%d.%m.%Y %H:%M:%S')}")

            st.info("**Aktueller Zeitplan:**\n")

            if st.button("🗑️ Zeitplan löschen"):
                clear_schedule()
                st.success("Zeitplan wurde gelöscht.")
                st.rerun()  # Seite neu laden, damit die Anzeige verschwindet

            interval_type = st.selectbox("Modus wählen", ["Täglich", "Stündlich", "Minütlich"])
            interval_value = 1
            crawl_time = None
            if interval_type == "Täglich":
                crawl_time = st.time_input("Uhrzeit für täglichen Crawl", value=datetime.time(2, 0))
            elif interval_type == "Stündlich":
                interval_value = st.number_input("Alle wie viele Stunden?", min_value=1, max_value=24, value=1)
            elif interval_type == "Minütlich":
                interval_value = st.number_input("Alle wie viele Minuten?", min_value=1, max_value=60, value=15)

            if st.button("🗓️ Zeitplan speichern"):
                start_scheduler(interval_type, interval_value, crawl_time)
                save_schedule_config(interval_type, interval_value, crawl_time)
                st.success("Zeitplan gespeichert und aktiviert.")
                st.rerun()

        with st.expander("⚙️ Einstellungen", expanded=False):
            openai_key = st.text_input(
                "🔑 OpenAI API Key",
                type="password",
                value=os.getenv("OPENAI_API_KEY", ""),
                key="openai_api_key_input"
            )
            reddit_client_id = st.text_input(
                "📘 Reddit Client ID",
                value=os.getenv("REDDIT_CLIENT_ID", ""),
                key="reddit_client_id_input"
            )
            reddit_secret = st.text_input(
                "📘 Reddit Secret",
                type="password",
                value=os.getenv("REDDIT_CLIENT_SECRET", ""),
                key="reddit_secret_input"
            )
            reddit_agent = st.text_input(
                "📘 Reddit User Agent",
                value=os.getenv("REDDIT_USER_AGENT", ""),
                key="reddit_agent_input"
            )
            subreddits = st.text_input(
                "📋 Subreddits",
                value=os.getenv("SUBREDDITS", "wallstreetbets"),
                key="subreddits_input"
            )
            gsheet_url = st.text_input(
                "🔗 Google Sheet URL",
                value=os.getenv("GSHEET_URL", ""),
                key="gsheet_url_input"
            )
            alpha_key = st.text_input(
                "Alpha Vantage API Key",
                value=os.getenv("ALPHAVANTAGE_API_KEY", ""),
                key="alpha_key_input"
            )
            discord_webhook = st.text_input(
                "📣 Discord Webhook URL",
                value=os.getenv("DISCORD_WEBHOOK_URL", ""),
                key="discord_webhook_input"
            )

            if st.button("💾 Einstellungen speichern", key="save_env_settings_btn"):
                update_dotenv_variable("OPENAI_API_KEY", openai_key, ENV_PATH)
                update_dotenv_variable("REDDIT_CLIENT_ID", reddit_client_id, ENV_PATH)
                update_dotenv_variable("REDDIT_CLIENT_SECRET", reddit_secret, ENV_PATH)
                update_dotenv_variable("REDDIT_USER_AGENT", reddit_agent, ENV_PATH)
                update_dotenv_variable("SUBREDDITS", subreddits, ENV_PATH)
                update_dotenv_variable("GSHEET_URL", gsheet_url, ENV_PATH)
                update_dotenv_variable("DISCORD_WEBHOOK_URL", discord_webhook, ENV_PATH)
                update_dotenv_variable("ALPHAVANTAGE_API_KEY", alpha_key, ENV_PATH)
                st.success("✅ Einstellungen gespeichert.")

        with st.expander("🐞 DEBUG", expanded=False):
            st.markdown("Technische Tools für Entwickler und Fehleranalyse.")

            # Button: Namensauflösung manuell starten
            if st.button("🔄 Ticker-Namensauflösung ausführen"):
                import subprocess
                result = subprocess.run(
                    ["python", "src/build_ticker_name_cache.py"],
                    capture_output=True, text=True
                )
                st.text(result.stdout)
                if result.returncode == 0:
                    st.success("Namensauflösung abgeschlossen!")
                else:
                    st.error("Fehler bei der Namensauflösung.")

            # Button: Discord-Benachrichtigung senden
            if st.button("📣 Test-Discord-Benachrichtigung senden"):
                pickle_files = list_pickle_files(PICKLE_DIR)
                if not pickle_files:
                    st.error("Keine Pickle-Datei gefunden.")
                else:
                    latest_pickle = sorted(pickle_files)[-1]
                    result = load_pickle(PICKLE_DIR / latest_pickle)
                    df_rows = []
                    for subreddit, srdata in result.get("subreddits", {}).items():
                        for symbol, count in srdata["symbol_hits"].items():
                            df_rows.append({"Ticker": symbol, "Subreddit": subreddit, "Nennungen": count})
                    df = pd.DataFrame(df_rows)
                    df["Unternehmen"] = df["Ticker"].map(name_map)
                    df_ticker = (
                        df.groupby(["Ticker", "Unternehmen"], as_index=False)["Nennungen"]
                        .sum()
                        .sort_values(by="Nennungen", ascending=False)
                    )
                    # Trend-Berechnung (optional für Test)
                    prev_nennungen = {}
                    summary_dict = {}
                    timestamp = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
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
                        st.success("Discord-Benachrichtigung gesendet!")
                    else:
                        st.error("Fehler beim Senden der Discord-Benachrichtigung.")

            if st.button("🧹 Crawl-Status zurücksetzen", key="reset_crawl_status_btn"):
                st.session_state["crawl_running"] = False
                st.session_state.pop("crawler_pid", None)
                clear_crawl_flag()
                st.success("Crawl-Status wurde zurückgesetzt!")
                st.rerun()

    with col_dashboard:
        # Hier kommt dein gesamtes Dashboard (alles außer build_env_editor())
        # Verschiebe den bisherigen Code aus main() hierher!
        # Entferne build_env_editor() aus dem Sidebar-Aufruf.
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or not api_key.strip():
            st.info("ℹ️ Bitte führe zunächst die initiale Konfiguration in den Einstellungen durch.")
            st.stop()

        if is_crawl_running() or st.session_state.get("crawl_running", False):
            if st.sidebar.button("🛑 Crawl stoppen"):
                stop_crawler()
                st.stop()
        else:
            if st.sidebar.button("🚀 Crawl jetzt starten"):
                start_crawler_and_wait()
                st.rerun()
                # Entferne

        # --- Live-Loganzeige für laufenden Crawl ---
        if is_crawl_running():
            st.info("🟡 Crawl läuft gerade ...")
            st.markdown("#### 📜 Live-Crawl-Log")
            log_box = st.empty()
            refresh_interval = 2  # Sekunden

            # Automatisches Polling für das Logfile
            import time
            for _ in range(150):  # z.B. 5 Minuten lang alle 2 Sekunden aktualisieren
                log_content = ""
                if LOG_PATH.exists():
                    try:
                        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                            log_content = f.read()
                    except Exception:
                        log_content = ""
                log_box.code(log_content, language="bash", height=400)
                time.sleep(refresh_interval)
                if not is_crawl_running():
                    break  # Crawl ist fertig, Schleife verlassen!
                st.rerun()  # <-- Workaround: Seite neu laden

        pickle_files = list_pickle_files(PICKLE_DIR)
        if not pickle_files:
            st.warning("📦 Keine Crawls vorhanden.")
            return

        configured_subs = [s.strip() for s in os.getenv("SUBREDDITS", "").split(",") if s.strip()]
        selected_subs = st.sidebar.multiselect("🌐 Subreddits filtern:", configured_subs, default=configured_subs)

        label_map = {}
        dated_items = []
        for f in pickle_files:
            try:
                ts = datetime.datetime.strptime(f.split("_")[0], "%y%m%d-%H%M%S")
                label = ts.strftime("%d.%m.%Y %H:%M Uhr")
                dated_items.append((ts, label, f))
            except:
                label = f
                dated_items.append((datetime.datetime.min, label, f))
            label_map[label] = f

        dated_items.sort(reverse=True)
        labels = [label for _, label, _ in dated_items]

        selected_label = st.sidebar.selectbox("📂 Analyse auswählen", labels, index=0)
        selected_pickle = label_map.get(selected_label)
        result = load_pickle(PICKLE_DIR / selected_pickle)

        # Logfile zum gewählten Run anzeigen
        logfile_path = find_log_for_pickle(selected_pickle)
        if logfile_path and os.path.exists(logfile_path):
            with st.expander("📜 Log dieses Crawls anzeigen", expanded=False):
                with open(logfile_path, "r", encoding="utf-8", errors="replace") as f:
                    st.code(f.read(), language="bash")
        else:
            # Fallback: Zeige das aktuelle Logfile, falls vorhanden
            if LOG_PATH.exists():
                with st.expander("📜 Aktuelles Logfile anzeigen", expanded=False):
                    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                        st.code(f.read(), language="bash")
            else:
                st.info("Kein Logfile für diesen Crawl gefunden.")

        # Lösch-Button für die aktuell ausgewählte Analyse
        if st.sidebar.button("🗑️ Analyse löschen"):
            to_delete = PICKLE_DIR / selected_pickle
            if to_delete.exists():
                to_delete.unlink()
                st.success(f"Analyse '{selected_label}' wurde gelöscht.")
                st.rerun()
            else:
                st.error("Datei nicht gefunden.")

        if "last_log" in st.session_state:
            with st.expander("📜 Letztes Crawl-Log anzeigen", expanded=False):
                st.code(st.session_state["last_log"], language="bash")

        df_rows = []
        for subreddit, srdata in result.get("subreddits", {}).items():
            for symbol, count in srdata["symbol_hits"].items():
                df_rows.append({
                    "Ticker": symbol,
                    "Subreddit": subreddit,
                    "Nennungen": count,
                    "Posts gecheckt": srdata.get("posts_checked", 0)
                })

        df = pd.DataFrame(df_rows)
        if df.empty:
            st.warning("😶 Keine Ticker-Daten.")
            return

        # Hier wird das aktuelle Mapping verwendet!
        df["Unternehmen"] = df["Ticker"].map(name_map)
        df = df[["Ticker", "Unternehmen", "Subreddit", "Nennungen", "Posts gecheckt"]]

        df = df[df["Subreddit"].isin(selected_subs)]
        selected_tickers = st.sidebar.multiselect("🎯 Ticker filtern:", sorted(df["Ticker"].unique()), default=sorted(df["Ticker"].unique()))
        df = df[df["Ticker"].isin(selected_tickers)]

        if df.empty:
            st.info("🔕 Kein Treffer.")
            return

        top_ticker = st.sidebar.selectbox("📌 Details für Ticker:", sorted(df["Ticker"].unique()))

        st.subheader("📊 Nennungen nach Subreddit")
        st.dataframe(df.sort_values(by="Nennungen", ascending=False), use_container_width=True)

        summary_path = find_summary_for(selected_pickle, SUMMARY_DIR)
        if not summary_path or not summary_path.exists():
            # Fallback: Versuche, die Datei direkt zu finden
            run_id = selected_pickle.split("_")[0]
            possible_path = SUMMARY_DIR / f"{run_id}_summary.md"
            if possible_path.exists():
                summary_path = possible_path

        summary_dict = {}
        if summary_path and summary_path.exists():
            summary_text = load_summary(summary_path)
            summary_dict = parse_summary_md(summary_text)

        needs_summary = False

        st.markdown(f"### 🧠 KI-Zusammenfassung für {top_ticker}")
        if summary_path and summary_path.exists():
            summary_text = load_summary(summary_path)
            summary_dict = parse_summary_md(summary_text)
            if top_ticker in summary_dict:
                st.success(summary_dict[top_ticker])
            else:
                st.warning("🟡 Keine Ticker-spezifische Zusammenfassung vorhanden.")
                needs_summary = True
        else:
            st.info("📭 Noch keine Zusammenfassung für dieses Crawl-Ergebnis.")
            needs_summary = True

        if needs_summary:
            with st.expander("📌 Wie funktioniert die Zusammenfassung?"):
                st.markdown("""
                Die KI-Zusammenfassung wird automatisch für Ticker mit ausreichender Relevanz erstellt.  
                Alternativ kannst du auch manuell eine Zusammenfassung für einen bestimmten Ticker auslösen.
                """)

            only_selected = st.checkbox("Nur diesen Ticker zusammenfassen", value=False)
            include_all = st.checkbox("Auch seltene Ticker einbeziehen (<5 Nennungen)", value=False)

            if st.button("✏️ Zusammenfassung jetzt erstellen"):
                with st.expander("📡 Live-Zusammenfassung läuft ...", expanded=True):
                    selected_symbols = [top_ticker] if only_selected else None
                    summarizer.generate_summary(
                        pickle_path=PICKLE_DIR / selected_pickle,
                        include_all=include_all,
                        streamlit_out=st,
                        only_symbols=selected_symbols
                    )
                    st.rerun()

        if summary_path and summary_path.exists():
            with st.expander("📃 Gesamte Zusammenfassung anzeigen"):
                st.markdown(load_summary(summary_path))

        wc_base = selected_pickle.split("_")[0]
        wc_path = CHART_DIR / f"{top_ticker}_wordcloud_{wc_base}.png"
        fallback_wc = CHART_DIR / f"{top_ticker}_wordcloud.png"
        image_path = wc_path if wc_path.exists() else fallback_wc
        if image_path.exists():
            st.image(Image.open(image_path), caption=f"Wordcloud für {top_ticker}", use_column_width=True)
        else:
            st.info("ℹ️ Keine Wordcloud vorhanden.")

        sentiment_path = CHART_DIR / "sentiment_bar_chart.png"
        if sentiment_path.exists():
            st.markdown("### 📉 Gesamt-Sentiment")
            st.image(sentiment_path, use_column_width=True)

        st.subheader("📊 Nennungen nach Ticker (gesamt)")
        df_ticker = (
            df.groupby(["Ticker", "Unternehmen"], as_index=False)["Nennungen"]
            .sum()
            .sort_values(by="Nennungen", ascending=False)
        )
        st.dataframe(df_ticker, use_container_width=True)

        # Top 3 Ticker für Discord-Benachrichtigung
        top3 = df_ticker["Ticker"].head(3).tolist()
        msg = f"Die Top 3 Ticker sind: {', '.join(top3)}"

        # Button für manuelle Benachrichtigung
        if st.button("📣 Discord-Benachrichtigung für diese Analyse senden"):
            try:
                # Hole die vorherige Analyse für Trend
                pickle_files = sorted(list_pickle_files(PICKLE_DIR))
                idx = pickle_files.index(selected_pickle)
                if idx > 0:
                    prev_pickle = pickle_files[idx-1]
                    prev_result = load_pickle(PICKLE_DIR / prev_pickle)
                    prev_rows = []
                    for subreddit, srdata in prev_result.get("subreddits", {}).items():
                        for symbol, count in srdata["symbol_hits"].items():
                            prev_rows.append({"Ticker": symbol, "Nennungen": count})
                    prev_df = pd.DataFrame(prev_rows)
                    prev_nennungen = prev_df.groupby("Ticker")["Nennungen"].sum().to_dict()
                else:
                    prev_nennungen = {}

                summary_path = find_summary_for(selected_pickle, SUMMARY_DIR)
                if not summary_path or not summary_path.exists():
                    # Fallback: Versuche, die Datei direkt zu finden
                    run_id = selected_pickle.split("_")[0]
                    possible_path = SUMMARY_DIR / f"{run_id}_summary.md"
                    if possible_path.exists():
                        summary_path = possible_path

                summary_dict = {}
                if summary_path and summary_path.exists():
                    summary_text = load_summary(summary_path)
                    summary_dict = parse_summary_md(summary_text)

                timestamp = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                msg = format_discord_message(
                    pickle_name=selected_pickle,
                    timestamp=timestamp,
                    df_ticker=df_ticker,
                    prev_nennungen=prev_nennungen,
                    name_map=name_map,
                    summary_dict=summary_dict
                )

                success = send_discord_notification(msg)
                if success:
                    st.success("Discord-Benachrichtigung gesendet!")
                else:
                    st.error("Fehler beim Senden der Discord-Benachrichtigung.")
            except Exception as e:
                st.error(f"Fehler beim Senden der Discord-Benachrichtigung: {e}")
            clear_crawl_flag()

        # Optional: Die alte Subreddit-Ansicht kannst du darunter als Detailansicht lassen.
        st.subheader("📊 Nennungen nach Subreddit (Detailansicht)")
        for subreddit in sorted(df["Subreddit"].unique()):
            subreddit_df = df[df["Subreddit"] == subreddit]
            total_mentions = subreddit_df["Nennungen"].sum()
            st.markdown(f"### {subreddit} (Gesamt: {total_mentions} Nennungen)")
            st.dataframe(subreddit_df.sort_values(by="Nennungen", ascending=False), use_container_width=True)

            # Optional: Zusammenfassung für den Subreddit anzeigen, falls vorhanden
            summary_path = find_summary_for(selected_pickle, SUMMARY_DIR)
            summary_dict = {}
            if summary_path and summary_path.exists():
                summary_text = load_summary(summary_path)
                summary_dict = parse_summary_md(summary_text)
                if subreddit in summary_dict:
                    st.success(summary_dict[subreddit])
                else:
                    st.info("Keine Subreddit-spezifische Zusammenfassung vorhanden.")
            else:
                st.info("Noch keine Zusammenfassung für dieses Crawl-Ergebnis.")

            st.markdown("---")

if __name__ == "__main__":
    main()

def update_dotenv_variable(key, value, dotenv_path):
    import os

    # Ordner anlegen, falls nicht vorhanden
    os.makedirs(os.path.dirname(dotenv_path), exist_ok=True)
    # Datei anlegen, falls nicht vorhanden
    if not os.path.exists(dotenv_path):
        with open(dotenv_path, "w", encoding="utf-8") as f:
            f.write("")

    # BUGFIX: Datei im Schreibmodus öffnen, falls sie leer ist
    if os.path.getsize(dotenv_path) == 0:
        lines = []
    else:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    found = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(dotenv_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ[key] = value
