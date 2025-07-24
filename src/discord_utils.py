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

def format_price_block_with_börse(prices):
    regular = prices.get("regular")
    kurs_1h_ago = prices.get("kurs_1h_ago")
    pre = prices.get("pre")
    post = prices.get("post")
    boerse_status = prices.get("boerse_status", "unbekannt")

    # Kursdifferenz
    diff = (regular - kurs_1h_ago) if (regular is not None and kurs_1h_ago is not None) else 0.0

    # Hauptkurs-String
    if regular is not None:
        kurs_str = f"{regular:.2f} USD ({diff:+.2f} USD) [{boerse_status}]"
    else:
        kurs_str = "keine Kursdaten verfügbar"

    # Pre-/After-Market
    pre_str = ""
    if pre is not None:
        pre_diff = pre - (kurs_1h_ago if kurs_1h_ago is not None else pre)
        pre_str = f" | Pre-Market: {pre:.2f} USD ({pre_diff:+.2f} USD)"
    if post is not None:
        post_diff = post - (kurs_1h_ago if kurs_1h_ago is not None else post)
        pre_str += f" | After-Market: {post:.2f} USD ({post_diff:+.2f} USD)"

    return kurs_str + pre_str