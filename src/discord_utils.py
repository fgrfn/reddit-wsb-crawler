import os
import requests
import logging
import time
from utils import list_pickle_files, load_pickle, load_ticker_names, find_summary_for

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

def format_discord_message(pickle_name, timestamp, df_ticker, prev_nennungen, name_map, summary_dict, next_crawl_time=None, openai_cost=None):
    platz_emojis = ["🥇", "🥈", "🥉"]
    next_crawl_str = f"{next_crawl_time}" if next_crawl_time else "unbekannt"
    warntext = "… [gekürzt wegen Discord-Limit]"
    maxlen = 2000

    kosten_str = ""
    if openai_cost is not None:
        kosten_str = f"\n💸 OpenAI Kosten heute: {openai_cost:.4f} USD\n"

    msg = (
        f"🕷️ Crawl abgeschlossen! 💾 {pickle_name} 🕒 {timestamp} ⏰ {next_crawl_str}"
        f"{kosten_str}\n"
        f"🏆 Top 3 Ticker:\n"
    )

    ticker_blocks = []
    for i, (_, row) in enumerate(df_ticker.head(3).iterrows(), 1):
        ticker = row["Ticker"]
        nennungen = row["Nennungen"]
        diff = nennungen - prev_nennungen.get(ticker, 0)
        trend = f"▲ (+{diff})" if diff > 0 else f"▼ ({diff})" if diff < 0 else "→ (0)"
        emoji = platz_emojis[i-1] if i <= 3 else ""
        kurs = row.get('Kurs')
        kurs_str = format_price_block_with_börse(kurs, ticker)
        unternehmen = row.get('Unternehmen', '') or name_map.get(ticker, '')
        block = (
            f"\n{emoji} {ticker} - {unternehmen}\n"
            f"🔢 {nennungen} {trend}\n"
            f"💵 {kurs_str}\n"
            f"🧠\n"
        )
        summary = summary_dict.get(str(ticker).strip().upper())
        if summary:
            block += summary.strip() + "\n"
        block += "\n"
        ticker_blocks.append(block)

    for i, block in enumerate(ticker_blocks):
        if i < 2:
            msg += block
        else:
            if len(msg) + len(block) > maxlen - len(warntext):
                split_idx = block.find("🧠 \n")
                if split_idx != -1:
                    head = block[:split_idx + len("🧠 \n")]
                    summary = block[split_idx + len("🧠 \n"):]
                    allowed = maxlen - len(msg) - len(warntext) - 2
                    summary = summary[:allowed] + warntext
                    block = head + summary + "\n\n"
                else:
                    block = block[:maxlen - len(msg) - len(warntext)] + warntext
            msg += block
            break

    if len(msg) > 2000:
        msg = msg[:2000 - len(warntext)] + warntext

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
    if symbol:
        kurs_str += f" | <https://finance.yahoo.com/quote/{symbol}>"
    return kurs_str

def get_discord_legend():
    return (
        "Legende:\n"
        "🔢 = Nennungen in Subreddits 🧠 = KI Zusammenfassungen\n"
        "💵 Kurs = letzter Börsenkurs 🌅 Pre-Market = vorbörslich 🌙 After-Market = nachbörslich\n"
        "💵 Kurs (+X.XX USD, +Y.YY%) = Veränderung zum Vortag | 📈 = gestiegen | 📉 = gefallen | ⏸️ = unverändert"
    )