import os
import requests
import logging
import time
from pathlib import Path
from utils import list_pickle_files, load_pickle, load_ticker_names, find_summary_for
import pandas as pd

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

def format_discord_message(
    pickle_name, timestamp, df_ticker, prev_nennungen, name_map, summary_dict,
    next_crawl_time=None
):
    platz_emojis = ["🥇", "🥈", "🥉"]
    next_crawl_str = f"{next_crawl_time}" if next_crawl_time else "unbekannt"
    warntext = "… [gekürzt wegen Discord-Limit]"
    maxlen = 2000

    top_n = min(3, len(df_ticker)) if hasattr(df_ticker, '__len__') else 3
    msg = (
        f"🕷️ Crawl abgeschlossen! 💾 {pickle_name} 🕒 {timestamp} ⏰ {next_crawl_str}\n"
        f"\n"
        f"🏆 Top {top_n} Ticker:\n"
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
    import time
    currency = kurs_data.get("currency", "USD")
    regular = kurs_data.get("regular")
    previous = kurs_data.get("previousClose") or kurs_data.get("previous")
    change = kurs_data.get("change")
    changePercent = kurs_data.get("changePercent")
    pre = kurs_data.get("pre")
    post = kurs_data.get("post")
    timestamp = kurs_data.get("timestamp")
    market_state = kurs_data.get("market_state")
    # trends
    t1 = kurs_data.get("change_1h")
    t24 = kurs_data.get("change_24h")
    t7 = kurs_data.get("change_7d")

    # emoji by change
    emoji = "❔"
    if change is not None:
        emoji = "📈" if change > 0 else "📉" if change < 0 else "⏸️"

    zeit = "unbekannt"
    if timestamp:
        try:
            zeit = time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))
        except Exception:
            pass

    if regular is not None:
        kurs_str = f"{regular:.2f} {currency} ({change:+.2f} {currency}, {changePercent:+.2f}%) {emoji} [{zeit}]"
    elif previous is not None:
        kurs_str = f"Vortag: {previous:.2f} {currency} [{zeit}]"
    else:
        kurs_str = "keine Kursdaten verfügbar"

    extras = []
    if pre is not None:
        extras.append(f"🌅 Pre-Market: {pre:.2f} {currency}")
    if post is not None:
        extras.append(f"🌙 After-Market: {post:.2f} {currency}")
    if extras:
        kurs_str += " | " + " | ".join(extras)

    if market_state:
        kurs_str += f" | Status: {market_state}"

    def tlabel(v):
        if v is None:
            return None
        arrow = "▲" if v > 0 else "▼" if v < 0 else "→"
        return f"{arrow} {v:+.2f}%"

    trend_parts = []
    if t1 is not None:
        trend_parts.append(f"1h {tlabel(t1)}")
    if t24 is not None:
        trend_parts.append(f"24h {tlabel(t24)}")
    if t7 is not None:
        trend_parts.append(f"7d {tlabel(t7)}")
    if trend_parts:
        kurs_str += " | Trends: " + " · ".join(trend_parts)

    symbol = kurs_data.get("symbol") or ticker or ""
    if symbol:
        kurs_str += f" | https://finance.yahoo.com/quote/{symbol}"
    return kurs_str

def format_tokens(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.1f}k"
    else:
        return str(n)


def build_test_message(
    ticker: str = "TEST",
    nennungen: int = 42,
    company: str = "Test Company GmbH",
    price: float = 12.34,
    change: float = 0.56,
    change_percent: float = 4.75,
    summary: str = "Das ist eine Test-Zusammenfassung.",
    # optional extended price info for preview
    pre: float | None = None,
    post: float | None = None,
    market_state: str | None = None,
    change_1h: float | None = None,
    change_24h: float | None = None,
    change_7d: float | None = None,
     pickle_name: str = "test_payload.pkl",
     timestamp: str = None,
     timestamp_unix: float = None,
     next_crawl_time: str = "unbekannt",
    openai_cost_crawl: float = 0.0,
):
    """Build a preview Discord message (string) using the existing formatter.

    Returns the rendered message string (does not send).
    """
    if timestamp is None:
        timestamp = time.strftime("%d.%m.%Y %H:%M:%S")

    # provide a unix timestamp for price block display if not provided
    if timestamp_unix is None:
        timestamp_unix = time.time()

    # Build a small DataFrame similar to what the crawler produces
    # try to resolve company name if not explicitly provided
    if company in (None, '', 'Test Company GmbH'):
        try:
            name_map = load_ticker_names(Path('data/input/ticker_name_map.pkl'))
            company = name_map.get(ticker, company)
        except Exception:
            pass
    # fallback to ticker if no company name could be resolved
    if not company:
        company = str(ticker)

    df = pd.DataFrame([
        {"Ticker": ticker, "Unternehmen": company, "Nennungen": nennungen, "Kurs": {
            "regular": price,
            "currency": "USD",
            "change": change,
            "changePercent": change_percent,
            "symbol": ticker,
            "timestamp": timestamp_unix,
            "pre": pre,
            "post": post,
            "market_state": market_state,
            "change_1h": change_1h,
            "change_24h": change_24h,
            "change_7d": change_7d,
        }}
    ])

    prev_nennungen = {ticker: max(0, nennungen - 5)}
    name_map = {ticker: company}
    summary_dict = {ticker: summary}

    msg = format_discord_message(
        pickle_name=pickle_name,
        timestamp=timestamp,
        df_ticker=df,
        prev_nennungen=prev_nennungen,
        name_map=name_map,
        summary_dict=summary_dict,
        next_crawl_time=next_crawl_time,
    )
    return msg


def send_test_notification(webhook_url: str = None, **kwargs) -> bool:
    """Build and send a test notification to the configured webhook (or given URL).

    Returns True on success, False on failure.
    """
    msg = build_test_message(**kwargs)
    return send_discord_notification(msg, webhook_url=webhook_url)

