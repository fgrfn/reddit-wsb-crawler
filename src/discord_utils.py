import os
import requests
import logging

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
    gesamt = df_ticker.head(3)["Nennungen"].sum()
    next_crawl_str = f"{next_crawl_time}"
    msg = (
        f"🕷️ Crawl abgeschlossen!\n"
        f"📦 Datei: {pickle_name}\n"
        f"🕒 Zeitpunkt: {timestamp} | nächster Crawl: {next_crawl_str}\n"
        f"\n"
        f"🏆 Top 3 Ticker:\n"
        f">━━━━━━━━━━━━━━━━━━━<\n"
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
        if kurs is not None:
            kurs_str = f"{kurs:.2f} USD"
        else:
            kurs_str = "k.A."
        unternehmen = row.get('Unternehmen', '') or name_map.get(ticker, '')
        msg += (
            f"\n{emoji} {i}. {ticker} \n"
            f"\n🏢 {unternehmen}\n"
            f"🔢 Nennungen: {nennungen} {trend}\n"
            f"💹 Kurs: {kurs_str}\n"
            f"🧠 Zusammenfassung:\n"
        )
        summary = summary_dict.get(ticker)
        if summary:
            msg += summary + "\n"
        msg += ">━━━━━━━━━━━━━━━━━━━<\n"
    return msg