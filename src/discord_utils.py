import os
import requests
import logging
import time
from datetime import datetime
from pathlib import Path
from utils import list_pickle_files, load_pickle, load_ticker_names, find_summary_for
import pandas as pd

def send_discord_notification(message, webhook_url=None, embed=None):
    """Sendet eine Discord-Nachricht als Text oder Rich Embed.
    
    Args:
        message: Nachrichtentext (wird ignoriert wenn embed gesetzt ist)
        webhook_url: Discord Webhook URL
        embed: Optional - Dict mit Discord Embed (siehe create_embed_*)
    """
    if webhook_url is None:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        logging.warning("Kein Discord-Webhook-URL gesetzt.")
        return False
    try:
        if embed:
            # Bei Embed: content muss leer sein, sonst wird beides angezeigt
            data = {"embeds": [embed], "content": None}
        else:
            data = {"content": message}
        response = requests.post(webhook_url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"❌ Discord-Benachrichtigung fehlgeschlagen: {e}")
        return False

def send_or_edit_discord_message(message, webhook_url=None, message_id=None, embed=None):
    """Sendet eine neue Nachricht oder editiert eine bestehende.
    
    Args:
        message: Nachrichtentext (wird ignoriert wenn embed gesetzt ist)
        webhook_url: Discord Webhook URL (optional, nutzt ENV wenn None)
        message_id: ID der zu editierenden Nachricht (optional)
        embed: Optional - Dict mit Discord Embed
    
    Returns:
        dict mit {"success": bool, "message_id": str} oder None bei Fehler
    """
    if webhook_url is None:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        logging.warning("Kein Discord-Webhook-URL gesetzt.")
        return None
    
    try:
        if embed:
            # Bei Embed: content muss leer oder null sein, sonst wird beides angezeigt
            data = {"embeds": [embed], "content": None}
        else:
            data = {"content": message}
        
        if message_id:
            # Editiere bestehende Nachricht
            # Format: https://discord.com/api/webhooks/WEBHOOK_ID/TOKEN/messages/MESSAGE_ID
            edit_url = f"{webhook_url}/messages/{message_id}"
            response = requests.patch(edit_url, json=data, timeout=10)
        else:
            # Sende neue Nachricht mit ?wait=true um message_id zu erhalten
            response = requests.post(f"{webhook_url}?wait=true", json=data, timeout=10)
        
        response.raise_for_status()
        
        if not message_id and response.status_code == 200:
            # Bei neuer Nachricht: ID aus Response extrahieren
            response_data = response.json()
            new_message_id = response_data.get("id")
            return {"success": True, "message_id": new_message_id}
        
        return {"success": True, "message_id": message_id}
    
    except Exception as e:
        logging.error(f"❌ Discord-Nachricht fehlgeschlagen: {e}")
        return None

def format_heartbeat_message(timestamp, run_id, total_posts, top_tickers, next_crawl_time="unbekannt", triggered_count=0, use_embed=True):
    """Erstellt eine kompakte Heartbeat/Status-Nachricht.
    
    Args:
        timestamp: Zeitstempel des Crawls
        run_id: Run-ID (z.B. "251210-143022")
        total_posts: Anzahl überprüfter Posts
        top_tickers: Liste von (ticker, count) Tupeln
        next_crawl_time: Nächster geplanter Crawl
        triggered_count: Anzahl ausgelöster Alerts
        use_embed: Wenn True, gibt embed-Dict zurück, sonst Text
    
    Returns:
        str oder dict: Text-Nachricht oder Discord Embed
    """
    import time
    from datetime import datetime
    
    # Berechne "vor X Minuten"
    try:
        # Parse timestamp (Format: "dd.mm.yyyy HH:MM:SS")
        dt = datetime.strptime(timestamp, "%d.%m.%Y %H:%M:%S")
        diff_seconds = (datetime.now() - dt).total_seconds()
        
        if diff_seconds < 60:
            time_ago = "vor wenigen Sekunden"
            status_emoji = "🟢"
            color = 0x00ff00  # Grün
        elif diff_seconds < 3600:
            mins = int(diff_seconds / 60)
            time_ago = f"vor {mins} Minute{'n' if mins != 1 else ''}"
            status_emoji = "🟢" if mins < 30 else "🟡"
            color = 0x00ff00 if mins < 30 else 0xffff00  # Grün/Gelb
        elif diff_seconds < 86400:
            hours = int(diff_seconds / 3600)
            time_ago = f"vor {hours} Stunde{'n' if hours != 1 else ''}"
            status_emoji = "🟡" if hours < 6 else "🔴"
            color = 0xffff00 if hours < 6 else 0xff0000  # Gelb/Rot
        else:
            days = int(diff_seconds / 86400)
            time_ago = f"vor {days} Tag{'en' if days != 1 else ''}"
            status_emoji = "🔴"
            color = 0xff0000  # Rot
    except Exception:
        time_ago = ""
        status_emoji = "💚"
        color = 0x00ff00
    
    if use_embed:
        # Discord Rich Embed
        embed = {
            "title": f"{status_emoji} WSB-Crawler Status",
            "color": color,
            "fields": [
                {
                    "name": "🕐 Letzter Crawl",
                    "value": f"{timestamp}\n{time_ago if time_ago else ''}",
                    "inline": True
                },
                {
                    "name": "📊 Posts überprüft",
                    "value": str(total_posts),
                    "inline": True
                },
                {
                    "name": "🔔 Alerts ausgelöst",
                    "value": str(triggered_count),
                    "inline": True
                }
            ],
            "footer": {
                "text": f"Run-ID: {run_id}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if next_crawl_time and next_crawl_time != "unbekannt":
            embed["fields"].append({
                "name": "⏭️ Nächster Crawl",
                "value": next_crawl_time,
                "inline": False
            })
        
        if top_tickers:
            top_text = "\n".join([f"`{i}.` **{ticker}**: {count}" for i, (ticker, count) in enumerate(top_tickers[:5], 1)])
            embed["fields"].append({
                "name": "🏆 Top 5 Erwähnungen",
                "value": top_text,
                "inline": False
            })
        
        return embed
    else:
        # Fallback: Text-Format (bisherige Version)
        lines = []
        lines.append(f"{status_emoji} **WSB-Crawler Status**")
        lines.append(f"🕐 Letzter Crawl: {timestamp}{(' (' + time_ago + ')') if time_ago else ''}")
        lines.append(f"📊 Posts überprüft: {total_posts}")
        lines.append(f"🔔 Alerts ausgelöst: {triggered_count}")
        
        if next_crawl_time and next_crawl_time != "unbekannt":
            lines.append(f"⏭️ Nächster Crawl: {next_crawl_time}")
        
        if top_tickers:
            lines.append("\n**Top 5 Erwähnungen:**")
            for i, (ticker, count) in enumerate(top_tickers[:5], 1):
                lines.append(f"{i}. {ticker}: {count}")
        
        lines.append(f"\n🆔 Run-ID: `{run_id}`")
        
        return "\n".join(lines)

def format_discord_message(
    pickle_name, timestamp, df_ticker, prev_nennungen, name_map, summary_dict,
    next_crawl_time=None, use_embed=True, **kwargs
):
    """Alert-Ansicht für Discord: zeigt Top-Ticker mit Kurs, Trends und Pre/Post-Market.
    
    Args:
        use_embed: Wenn True, gibt Discord Embed zurück (schöner), sonst Text
    
    Returns:
        dict (embed) oder str (text message)
    """
    platz_emojis = ["🥇", "🥈", "🥉"]
    when = timestamp or "unbekannt"
    # Schwelle für Hervorhebung (env oder default)
    try:
        alert_delta = float(os.getenv("ALERT_MIN_DELTA", "10"))
    except Exception:
        alert_delta = 10.0

    # Top-N (max 3)
    top_n = min(3, len(df_ticker)) if hasattr(df_ticker, '__len__') else 3
    
    if use_embed:
        # Discord Rich Embed Version
        embed = {
            "title": "⚠️ WSB-ALARM — Ungewöhnliche Aktivität",
            "description": f"📅 {when}",
            "color": 0xff6b00,  # Orange für Alerts
            "fields": [],
            "footer": {"text": f"💾 {pickle_name}" if pickle_name else "WSB Crawler"},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        for i, (_, row) in enumerate(df_ticker.head(top_n).iterrows(), 1):
            ticker = row["Ticker"]
            nennungen = row["Nennungen"]
            prev = prev_nennungen.get(ticker, 0)
            diff = nennungen - prev
            rank_emoji = platz_emojis[i-1] if i <= 3 else f"{i}."
            highlight = " 🚨" if diff >= alert_delta else ""
            
            unternehmen = row.get('Unternehmen', '') or name_map.get(ticker, '')
            
            # Ticker-Header als Feld-Titel
            field_name = f"{rank_emoji} {ticker}{highlight}"
            if unternehmen:
                field_name += f" — {unternehmen}"
            
            # Kurs-Informationen
            kurs = row.get("Kurs") or {}
            kurs_info = []
            
            regular = kurs.get("regular")
            change = kurs.get("change")
            changePercent = kurs.get("changePercent")
            currency = kurs.get("currency", "USD")
            
            if regular is not None:
                emoji = "📈" if change and change > 0 else "📉" if change and change < 0 else "⏸️"
                kurs_info.append(f"{emoji} **{regular:.2f} {currency}** ({change:+.2f}, {changePercent:+.2f}%)")
            
            # Pre/Post-Market
            pre = kurs.get("pre")
            post = kurs.get("post")
            if pre:
                kurs_info.append(f"🌅 Pre: {pre:.2f} {currency}")
            if post:
                kurs_info.append(f"🌙 After: {post:.2f} {currency}")
            
            # Trends
            trend_parts = []
            for period, key in [("1h", "change_1h"), ("24h", "change_24h"), ("7d", "change_7d")]:
                val = kurs.get(key)
                if val is not None:
                    arrow = "▲" if val > 0 else "▼" if val < 0 else "→"
                    trend_parts.append(f"{period}: {arrow}{val:+.2f}%")
            
            if trend_parts:
                kurs_info.append("📊 " + " · ".join(trend_parts))
            
            # Nennungen
            field_value = f"🔢 **{nennungen}** Nennungen (Δ **{diff:+d}**)\n"
            field_value += "\n".join(kurs_info)
            
            # Summary (optional)
            entry = summary_dict.get(str(ticker).strip().upper())
            if entry:
                if isinstance(entry, dict):
                    summ = entry.get("summary", "") or ""
                    news = entry.get("news", []) or []
                else:
                    summ = str(entry)
                    news = []
                
                if summ:
                    s = summ.strip().replace("\n", " ")
                    if len(s) > 150:
                        s = s[:147].rstrip() + "…"
                    field_value += f"\n💡 {s}"
                
                # Erste News-Headline (optional)
                if news and len(news) > 0:
                    first_news = news[0]
                    title = first_news.get("title") or first_news.get("headline") or ""
                    if title:
                        if len(title) > 100:
                            title = title[:97].rstrip() + "…"
                        field_value += f"\n📰 {title}"
            
            # Yahoo Finance Link
            symbol = kurs.get("symbol") or ticker
            field_value += f"\n[📊 Yahoo Finance](https://finance.yahoo.com/quote/{symbol})"
            
            embed["fields"].append({
                "name": field_name,
                "value": field_value,
                "inline": False
            })
        
        return embed
    
    else:
        # Fallback: Text-Format (bisherige Version)
        lines = []
        lines.append("⚠️ WSB-ALARM — Ungewöhnliche Aktivität entdeckt")
        if pickle_name:
            lines.append(f"💾 {pickle_name}")
        lines.append(f"⏰ {when}")
        lines.append("")

        for i, (_, row) in enumerate(df_ticker.head(top_n).iterrows(), 1):
            ticker = row["Ticker"]
            nennungen = row["Nennungen"]
            prev = prev_nennungen.get(ticker, 0)
            diff = nennungen - prev
            rank_emoji = platz_emojis[i-1] if i <= 3 else ""
            highlight = " 🚨" if diff >= alert_delta else ""
            unternehmen = row.get('Unternehmen', '') or name_map.get(ticker, '')
            lines.append(f"{rank_emoji} {ticker} - {unternehmen}{highlight}")
            lines.append(f"🔢 Nennungen: {nennungen} (Δ {diff:+d})")
            kurs = row.get("Kurs") or {}
            kurs_str = format_price_block_with_börse(kurs, ticker)
            lines.append(f"💵 {kurs_str}")
            entry = summary_dict.get(str(ticker).strip().upper())
            if entry:
                if isinstance(entry, dict):
                    summ = entry.get("summary", "") or ""
                    news = entry.get("news", []) or []
                else:
                    summ = str(entry)
                    news = []

                if summ:
                    s = summ.strip().replace("\n", " ")
                    if len(s) > 200:
                        s = s[:197].rstrip() + "…"
                    lines.append(f"🧠 {s}")

                if news:
                    max_head = 3
                    for art in news[:max_head]:
                        title = art.get("title") or art.get("headline") or ""
                        src = art.get("source") or art.get("source_name") or ""
                        url = art.get("url") or art.get("link") or ""
                        short = title
                        if len(short) > 140:
                            short = short[:137].rstrip() + "…"
                        if src:
                            short = f"{short} ({src})"
                        if url:
                            short = f"{short} | {url}"
                        lines.append(f"📰 {short}")
            lines.append("---")

        if lines and lines[-1] == "---":
            lines.pop()

        msg = "\n".join(lines)
        if len(msg) > 1900:
            msg = msg[:1900].rstrip() + "\n… [gekürzt]"
        return msg

    # Entferne letzte Trennlinie
    if lines and lines[-1] == "---":
        lines.pop()

    # Baue Nachricht zusammen, achte auf Discord-Limit ~2000 Zeichen
    msg = "\n".join(lines)
    if len(msg) > 1900:
        msg = msg[:1900].rstrip() + "\n… [gekürzt]"
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
    # optional news items for preview: list[dict] with keys title/source/url
    news: list | None = None,
    pickle_name: str = "test_payload.pkl",
    timestamp: str = None,
    timestamp_unix: float = None,
    next_crawl_time: str = "unbekannt",
):
    """Build a preview Discord message (string) using the existing formatter.

    Returns the rendered message string (does not send).
    """
    import time
    import pandas as pd

    if timestamp is None:
        timestamp = time.strftime("%d.%m.%Y %H:%M:%S")

    # provide a unix timestamp for price block display if not provided
    if timestamp_unix is None:
        timestamp_unix = time.time()

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
    # provide summary as dict with optional news so formatter shows headlines
    summary_dict = {ticker: {"summary": summary, "news": news or []}}

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

