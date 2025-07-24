import os
import requests
import logging
import time
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
        f"• Kurs = letzter Börsenkurs | 🌅 Pre-Market = vorbörslich | 🌙 After-Market = nachbörslich\n"
        f"• (+X.XX USD, +Y.YY%) = Veränderung zum Vortag\n"
        f"• 📈 = gestiegen | 📉 = gefallen | ⏸️ = unverändert\n"
        f"\n"  # <--- Zusätzliche Leerzeile für Absatz!
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
        kurs_str = row.get('KursStr', 'keine Kursdaten verfügbar')  # <-- nur noch KursStr verwenden!
        unternehmen = name_map.get(ticker, "-")
        yahoo_url = f"https://finance.yahoo.com/quote/{ticker}"
        msg += (
            f"\n{emoji} [{ticker}]({yahoo_url}) - {unternehmen}\n"
            f"🔢 Nennungen: {nennungen} {trend}\n"
            f"💵 Kurs: {kurs_str}\n"
            f"🧠 Zusammenfassung:\n"
        )
        summary = summary_dict.get(ticker)
        if summary:
            msg += summary.strip() + "\n"
        msg += "\n"
    return msg

def format_price_block_with_börse(kurs_data, ticker=None):
    if not isinstance(kurs_data, dict):
        return "keine Kursdaten verfügbar"
    currency = kurs_data.get("currency", "USD")
    regular = kurs_data.get("regular")
    previous = kurs_data.get("previousClose")
    change = kurs_data.get("change")
    changePercent = kurs_data.get("changePercent")
    pre = kurs_data.get("pre")
    post = kurs_data.get("post")
    timestamp = kurs_data.get("timestamp")
    # Emoji je nach Kursentwicklung
    if change is not None:
        if change > 0:
            emoji = "📈"
        elif change < 0:
            emoji = "📉"
        else:
            emoji = "⏸️"
    else:
        emoji = "❔"
    # Zeitformat
    if timestamp:
        zeit = time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))
    else:
        zeit = "unbekannt"
    # Hauptkurs
    if regular is not None:
        kurs_str = f"{regular:.2f} {currency} ({change:+.2f} {currency}, {changePercent:+.2f}%) {emoji} [{zeit}]"
    elif previous is not None:
        kurs_str = f"Vortag: {previous:.2f} {currency} [{zeit}]"
    else:
        kurs_str = "keine Kursdaten verfügbar"
    # Pre-/After-Market
    if pre is not None:
        kurs_str += f" | 🌅 Pre-Market: {pre:.2f} {currency}"
    if post is not None:
        kurs_str += f" | 🌙 After-Market: {post:.2f} {currency}"
    # Yahoo-Link (Ticker als Fallback, falls symbol nicht im Kursdict)
    symbol = kurs_data.get('symbol') or ticker or ""
    if regular is not None and symbol:
        kurs_str += f" | [Yahoo Finance](https://finance.yahoo.com/quote/{symbol})"
    return kurs_str