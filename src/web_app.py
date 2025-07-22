import os
import re
import sys
import time
import pickle
import subprocess
import datetime
import pandas as pd
import streamlit as st
from reddit_crawler import reddit_crawler
from pathlib import Path
from collections import Counter
from PIL import Image
import threading
import schedule
BASE_DIR = Path(__file__).resolve().parent.parent
PICKLE_DIR = BASE_DIR / "data" / "output" / "pickle"
SUMMARY_DIR = BASE_DIR / "data" / "output" / "summaries"
CHART_DIR = BASE_DIR / "data" / "output" / "charts"
EXCEL_PATH = BASE_DIR / "data" / "output" / "excel" / "ticker_sentiment_summary.xlsx"
LOG_PATH = BASE_DIR / "logs" / "crawler.log"
ARCHIVE_DIR = LOG_PATH.parent / "archive"
from dotenv import load_dotenv
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
import summarizer
from discord_utils import send_discord_notification

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / "config" / ".env"
TICKER_NAME_PATH = BASE_DIR / "data" / "input" / "ticker_name_map.pkl"
name_map = load_ticker_names(TICKER_NAME_PATH)

load_dotenv(dotenv_path=ENV_PATH)

def build_env_editor():
    st.sidebar.markdown("---")
    with st.sidebar.expander("⚙️ Einstellungen", expanded=False):
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

def start_crawler_and_wait():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("🕷️ Crawl gestartet ...\n")

    # Logfile-Handle sofort wieder schließen!
    with open(LOG_PATH, "a", encoding="utf-8") as log_handle:
        crawler_proc = subprocess.Popen(
            [sys.executable, "src/main_crawler.py"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
            close_fds=True  # wichtig für Windows!
        )

    status = st.status("🕷️ Crawler läuft ...", expanded=True)
    with st.expander("📜 Crawl-Log anzeigen", expanded=True):
        log_view = st.empty()
        log_content = ""

        existing = set(list_pickle_files(PICKLE_DIR))
        timeout = 300
        start_time = time.time()

        while time.time() - start_time < timeout:
            if LOG_PATH.exists():
                try:
                    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                        log_content = f.read()
                except Exception as e:
                    log_content = f"Fehler beim Lesen des Logs: {e}"

                log_view.code(log_content, language="bash", height=400)
                st.session_state["last_log"] = log_content

            current = set(list_pickle_files(PICKLE_DIR))
            diff = current - existing
            if diff:
                new_pickle = sorted(diff)[0]
                status.update(label="✅ Crawl abgeschlossen", state="complete")
                st.success(f"Neue Analyse geladen: `{new_pickle}`")
                crawler_proc.wait()
                time.sleep(0.5)  # Kurze Pause

                # Robust: Logfile mehrfach versuchen zu archivieren
                for _ in range(5):
                    try:
                        archive_log(LOG_PATH, ARCHIVE_DIR)
                        break
                    except PermissionError:
                        time.sleep(0.5)
                else:
                    st.error("Konnte Logfile nicht archivieren (noch gesperrt).")

                # Discord-Benachrichtigung mit Top 3 Zusammenfassungen und Nennungs-Delta
                try:
                    result = load_pickle(PICKLE_DIR / new_pickle)
                    summary_path = find_summary_for(new_pickle, SUMMARY_DIR)
                    summary_dict = {}
                    if summary_path and summary_path.exists():
                        summary_text = load_summary(summary_path)
                        summary_dict = parse_summary_md(summary_text)
                    # Top 3 Ticker nach Nennungen
                    df_rows = []
                    for subreddit, srdata in result.get("subreddits", {}).items():
                        for symbol, count in srdata["symbol_hits"].items():
                            df_rows.append({
                                "Ticker": symbol,
                                "Nennungen": count
                            })
                    df = pd.DataFrame(df_rows)
                    top3 = (
                        df.groupby("Ticker")["Nennungen"]
                        .sum()
                        .sort_values(ascending=False)
                        .head(3)
                        .index.tolist()
                    )
                    # Vorherigen Crawl laden (sofern vorhanden)
                    pickle_files = list_pickle_files(PICKLE_DIR)
                    prev_pickle = None
                    if len(pickle_files) > 1:
                        prev_pickle = sorted([f for f in pickle_files if f != new_pickle], reverse=True)[0]
                    prev_counts = {}
                    if prev_pickle:
                        prev_result = load_pickle(PICKLE_DIR / prev_pickle)
                        prev_rows = []
                        for subreddit, srdata in prev_result.get("subreddits", {}).items():
                            for symbol, count in srdata["symbol_hits"].items():
                                prev_rows.append({
                                    "Ticker": symbol,
                                    "Nennungen": count
                                })
                        prev_df = pd.DataFrame(prev_rows)
                        prev_counts = prev_df.groupby("Ticker")["Nennungen"].sum().to_dict()
                    msg = f"🕷️ Crawl abgeschlossen: Neue Analyse `{new_pickle}` ist verfügbar.\n"
                    for ticker in top3:
                        nennungen = int(df[df["Ticker"] == ticker]["Nennungen"].sum())
                        prev = prev_counts.get(ticker, 0)
                        delta = nennungen - prev
                        delta_str = ""
                        if prev > 0:
                            if delta > 0:
                                delta_str = f" (▲ +{delta})"
                            elif delta < 0:
                                delta_str = f" (▼ {delta})"
                            else:
                                delta_str = " (–)"
                        else:
                            delta_str = " (neu)"
                        summary = summary_dict.get(ticker, "Keine Zusammenfassung vorhanden.")
                        msg += f"\n**{ticker}**: {nennungen} Nennungen{delta_str}\n{summary}\n"
                    send_discord_notification(msg, os.getenv("DISCORD_WEBHOOK_URL", ""))
                except Exception as e:
                    print(f"❌ Discord-Benachrichtigung (mit Zusammenfassungen) fehlgeschlagen: {e}")

                st.rerun()
                break

            if crawler_proc.poll() is not None:
                break

            time.sleep(2)
        else:
            status.update(label="⚠️ Timeout – keine neue Datei gefunden", state="error")
            st.error("Der Crawler hat keine neue Analyse erzeugt.")

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

        # Resolver mit Einzel-Feedback
        from reddit_crawler import resolve_ticker_name, load_ticker_name_map
        cache = load_ticker_name_map()

        for i, sym in enumerate(tickers):
            sym_clean, name = resolve_ticker_name(sym, cache, verbose=True)
            results[sym_clean] = name
            update_progress(i, sym)
            sleep(0.1)  # optional bremsen

        progress.empty()
        status.success("Alle Ticker verarbeitet.")

        st.subheader("📋 Ergebnis:")
        st.table({k: v or "❌ Nicht gefunden" for k, v in results.items()}.items())

        # Optional: CSV-Download anbieten
        import pandas as pd
        df = pd.DataFrame(list(results.items()), columns=["Symbol", "Firmenname"])
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Als CSV herunterladen", csv, "ticker_results.csv", "text/csv")

scheduler_thread = None

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

    while True:
        schedule.run_pending()
        time.sleep(10)

def start_scheduler(interval_type, interval_value, crawl_time=None):
    global scheduler_thread
    if scheduler_thread and scheduler_thread.is_alive():
        st.warning("Zeitplaner läuft bereits.")
        return
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
    schedule.clear()

def main():
    st.set_page_config(page_title="Reddit Crawler Dashboard", layout="wide")
    st.title("🕷️ Reddit Crawler Dashboard")

    col_dashboard, col_settings = st.columns([3, 1])

    with col_settings:
        with st.expander("🕒 Zeitplanung", expanded=True):
            st.markdown("Hier kannst du den automatischen Start des Crawlers planen.")

            st.info("**Aktueller Zeitplan:**\n" + get_schedule_description())

            if st.button("🗑️ Zeitplan löschen"):
                clear_schedule()
                st.success("Zeitplan wurde gelöscht.")

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
                st.success("Zeitplan gespeichert und aktiviert.")

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
            st.markdown("Hier findest du technische Tools für Entwickler und Fehleranalyse.")
            if st.button("🔄 Ticker-Namen auflösen"):
                result = subprocess.run([sys.executable, "src/resolve_latest_hits.py"])
                if result.returncode == 0:
                    st.success("Ticker-Namen wurden erfolgreich aufgelöst.")
                    st.rerun()
                else:
                    st.error("Fehler beim Auflösen der Ticker-Namen.")

    with col_dashboard:
        # Hier kommt dein gesamtes Dashboard (alles außer build_env_editor())
        # Verschiebe den bisherigen Code aus main() hierher!
        # Entferne build_env_editor() aus dem Sidebar-Aufruf.
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or not api_key.strip():
            st.info("ℹ️ Bitte führe zunächst die initiale Konfiguration in den Einstellungen durch.")
            st.stop()

        if st.sidebar.button("🚀 Crawl jetzt starten"):
            start_crawler_and_wait()
            st.stop()

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
        summary_dict = {}
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

        st.markdown("### 📁 Datenexport")
        col1, col2 = st.columns(2)

        if EXCEL_PATH.exists():
            with open(EXCEL_PATH, "rb") as f:
                col1.download_button(
                    label="⬇️ Excel-Datei herunterladen",
                    data=f,
                    file_name="sentiment_summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            col1.info("📄 Keine Excel-Datei gefunden.")

        sheet_url = os.getenv("GSHEET_URL", "")
        if sheet_url:
            col2.link_button("🔗 Google Sheet öffnen", url=sheet_url)
        else:
            col2.info("🔗 Kein Google Sheet konfiguriert.")

        st.caption(f"📂 Datenbasis: {selected_pickle}")


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

    # Rest wie gehabt ...
    with open(dotenv_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    # ...existing code...

import glob

def find_log_for_pickle(pickle_filename):
    # Extrahiere Zeitstempel aus Pickle-Dateiname
    ts = pickle_filename.split("_")[0]
    # Suche nach Logfile mit gleichem Zeitstempel im Archiv
    pattern = str(ARCHIVE_DIR / f"{ts}_*.log")
    matches = glob.glob(pattern)
    return matches[0] if matches else None
