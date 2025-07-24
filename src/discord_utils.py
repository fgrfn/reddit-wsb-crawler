import os
import requests
import logging
from utils import list_pickle_files, load_pickle, load_ticker_names

def send_discord_notification(message, webhook_url=None):
    if webhook_url is None:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        logging.warning("Kein Discord-Webhook-URL gesetzt.")
        return False
    try:
        data = {"content": message}
        response = requests.post(webhook_url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"❌ Discord-Benachrichtigung fehlgeschlagen: {e}")
        return False

def format_discord_message(pickle_name, timestamp, df_ticker, prev_nennungen, name_map, summary_dict, next_crawl_time=None):
    platz_emojis = ["🥇", "🥈", "🥉"]
    next_crawl_str = f"{next_crawl_time}" if next_crawl_time else "None"
    msg = (
        f"🕷️ Crawl abgeschlossen!\n"
        f"📦 Datei: {pickle_name}\n"
        f"🕒 Zeitpunkt: {timestamp} | nächster Crawl: {next_crawl_str}\n\n"
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
        marktstatus = row.get('Marktstatus')
        kurs_regular = row.get('KursRegular')
        kurs_str = ""
        if kurs_regular is not None and marktstatus:
            kurs_str = f"{kurs_regular:.2f} USD → {kurs:.2f} USD ({marktstatus})"
        elif kurs is not None:
            kurs_str = f"{kurs:.2f} USD"
        else:
            kurs_str = "keine Kursdaten verfügbar"
        # Link zu Yahoo Finance
        yahoo_url = f"https://finance.yahoo.com/quote/{ticker}"
        msg += (
            f"\n{emoji} [{ticker}]({yahoo_url}) - {unternehmen}\n"
            f"🔢 Nennungen: {nennungen} {trend}\n"
            f"💹 Kurs: {kurs_str}\n"
            f"🧠 Zusammenfassung:\n"
        )
        summary = summary_dict.get(ticker)
        if summary:
            msg += summary.strip() + "\n"
        msg += "\n"
    return msg