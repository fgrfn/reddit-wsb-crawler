"""
Discord-Integration: Alerts als Rich Embeds, Heartbeat-Status-Updates.

Nutzt httpx direkt (kein discord.py für Webhooks nötig).
Rate-Limit-Handling: Discord erlaubt 5 Requests pro 2 Sekunden pro Webhook.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from wsb_crawler.config import Settings, get_settings
from wsb_crawler.models import Alert, AlertReason, MarketStatus, RunStatus, TrendEntry

if TYPE_CHECKING:
    from wsb_crawler.storage.database import Database

_db: "Database | None" = None


def set_database(db: "Database") -> None:
    global _db
    _db = db

# Discord Embed-Farben
COLOR_SPIKE = 0xFF4500       # Reddit-Orange
COLOR_NEW = 0x00B0F4         # Blau
COLOR_PRICE_MOVE = 0xFFAA00  # Amber
COLOR_HEARTBEAT = 0x2B2D31   # Discord-Dunkel
COLOR_SUCCESS = 0x57F287     # Grün

TREND_EMOJI = {"up": "📈", "down": "📉", "flat": "➡️"}
MARKET_LABEL = {
    MarketStatus.PRE_MARKET: "Pre-Market",
    MarketStatus.OPEN: "Offen",
    MarketStatus.AFTER_HOURS: "After-Hours",
    MarketStatus.CLOSED: "Geschlossen",
}


def _format_price(value: float | None, currency: str = "USD") -> str:
    if value is None:
        return "—"
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{symbol}{value:,.2f}"


def _format_change(pct: float | None) -> str:
    if pct is None:
        return "—"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _build_alert_embed(alert: Alert, cfg: Settings) -> dict:
    """Erstellt ein Discord Rich Embed für einen Alert."""
    spike = alert.spike
    price = spike.price_data

    # Farbe je nach Reason
    color = {
        AlertReason.NEW_TICKER: COLOR_NEW,
        AlertReason.SPIKE: COLOR_SPIKE,
        AlertReason.PRICE_MOVE: COLOR_PRICE_MOVE,
    }.get(alert.reason, COLOR_SPIKE)

    reason_label = {
        AlertReason.NEW_TICKER: "🆕 Neuer Ticker",
        AlertReason.SPIKE: "🚀 Spike erkannt",
        AlertReason.PRICE_MOVE: "💹 Kurs + Aktivität",
    }.get(alert.reason, "⚡ Alert")

    company = price.company_name if price else None
    title = f"{reason_label}: **${alert.ticker}**"
    if company:
        title += f" — {company}"

    fields = []

    # Mentions-Block
    mention_text = f"**{spike.current_mentions}**"
    if not spike.is_new:
        mention_text += f"\n∅ {spike.avg_mentions:.1f}/Lauf ({spike.ratio:.1f}x)"
        mention_text += f"\n+{spike.delta} mehr als normal"
    fields.append({"name": "📊 Erwähnungen", "value": mention_text, "inline": True})

    # Kurs-Block
    if price:
        market_label = MARKET_LABEL.get(price.market_status, "—")
        price_text = f"**{_format_price(price.primary_price, price.currency)}**"
        if price.primary_change is not None:
            price_text += f"\n{_format_change(price.primary_change)} (24h)"
        if price.change_1h is not None:
            price_text += f"\n{_format_change(price.change_1h)} (1h)"
        if price.change_7d is not None:
            price_text += f"\n{_format_change(price.change_7d)} (7d)"
        price_text += f"\n_{market_label}_"
        fields.append({"name": "💰 Kurs", "value": price_text, "inline": True})

    # Kursverläufe (1h/24h/7d) als kompakte Zeile
    if price and any(v is not None for v in [price.change_1h, price.change_24h, price.change_7d]):
        bars = []
        if price.change_1h is not None:
            bars.append(f"1h: {_format_change(price.change_1h)}")
        if price.change_24h is not None:
            bars.append(f"24h: {_format_change(price.change_24h)}")
        if price.change_7d is not None:
            bars.append(f"7d: {_format_change(price.change_7d)}")
        fields.append({"name": "📉 Trend", "value": "  |  ".join(bars), "inline": False})

    # News-Block (max. 3 Headlines)
    if spike.news:
        news_lines = []
        for article in spike.news[:3]:
            age_h = (datetime.now(tz=timezone.utc) - article.published_at).total_seconds() / 3600
            age_str = f"{int(age_h)}h" if age_h < 24 else f"{int(age_h/24)}d"
            news_lines.append(f"[{article.title[:70]}...]({article.url}) _{age_str}_")
        fields.append({
            "name": "📰 Aktuelle News",
            "value": "\n".join(news_lines),
            "inline": False,
        })

    # Footer
    subreddits = ", ".join(f"r/{s}" for s in cfg.crawler.subreddits)
    footer = f"WSB-Crawler v2 • {subreddits}"

    return {
        "title": title,
        "color": color,
        "fields": fields,
        "footer": {"text": footer},
        "timestamp": alert.triggered_at.isoformat(),
    }


def _build_heartbeat_embed(status: RunStatus) -> dict:
    """Status-Update Embed (kein Ping, silent)."""
    if status.last_run_at:
        last_run_str = f"<t:{int(status.last_run_at.timestamp())}:R>"
        duration_str = (
            f"{status.last_run_duration_seconds:.0f}s"
            if status.last_run_duration_seconds else "—"
        )
    else:
        last_run_str = "—"
        duration_str = "—"

    fields = [
        {"name": "⏱ Letzter Lauf", "value": last_run_str, "inline": True},
        {"name": "⏳ Dauer", "value": duration_str, "inline": True},
        {"name": "🔔 Alerts gesamt", "value": str(status.total_alerts_sent), "inline": True},
        {"name": "📌 Ticker getrackt", "value": str(status.tracked_tickers), "inline": True},
        {"name": "🔄 Läufe gesamt", "value": str(status.total_runs), "inline": True},
    ]

    if status.next_run_at:
        fields.append({
            "name": "⏭ Nächster Lauf",
            "value": f"<t:{int(status.next_run_at.timestamp())}:R>",
            "inline": True,
        })

    return {
        "title": "💓 WSB-Crawler Status",
        "color": COLOR_HEARTBEAT,
        "fields": fields,
        "footer": {"text": "WSB-Crawler v2 • Automatischer Heartbeat"},
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


async def _send_webhook(
    payload: dict,
    webhook_url: str,
    retries: int = 3,
    wait: bool = False,
) -> str | bool:
    """Sendet eine Nachricht an den Discord-Webhook mit Rate-Limit-Handling.

    Args:
        wait: Wenn True, wird ?wait=true übergeben und die Message-ID (str) zurückgegeben.
              Bei Fehler wird False zurückgegeben.
    """
    url = f"{webhook_url}?wait=true" if wait else webhook_url

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)

                if response.status_code == 429:
                    retry_after = float(response.json().get("retry_after", 2.0))
                    logger.warning(f"Discord Rate-Limit — warte {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                if wait:
                    return str(response.json()["id"])
                return True

        except Exception as e:
            backoff = 2 ** attempt
            logger.warning(f"Discord-Webhook Fehler (Versuch {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(backoff)

    return False


async def _edit_webhook_message(
    payload: dict,
    webhook_url: str,
    message_id: str,
) -> bool:
    """Bearbeitet eine bestehende Webhook-Nachricht via PATCH.

    Gibt False zurück wenn die Nachricht nicht mehr existiert (z.B. manuell gelöscht).
    """
    # Webhook-URL: https://discord.com/api/webhooks/{id}/{token}
    edit_url = f"{webhook_url}/messages/{message_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(edit_url, json=payload)
            if response.status_code == 404:
                logger.debug("Heartbeat-Nachricht nicht mehr vorhanden — wird neu erstellt")
                return False
            if response.status_code == 429:
                retry_after = float(response.json().get("retry_after", 2.0))
                logger.warning(f"Discord Rate-Limit beim Editieren — warte {retry_after}s")
                await asyncio.sleep(retry_after)
                # Einmal wiederholen
                response = await client.patch(edit_url, json=payload)
            response.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"Discord-Nachricht konnte nicht bearbeitet werden: {e}")
        return False


async def send_alert(alert: Alert) -> bool:
    """Sendet einen Alert als Discord Rich Embed."""
    cfg = await get_settings(_db)
    embed = _build_alert_embed(alert, cfg)
    payload = {
        "username": "WSB-Crawler",
        "embeds": [embed],
    }
    success = await _send_webhook(payload, cfg.discord.webhook_url)
    if success:
        alert.sent = True
        logger.info(f"Alert gesendet: ${alert.ticker}")
    else:
        logger.error(f"Alert konnte nicht gesendet werden: ${alert.ticker}")
    return success


async def send_alerts(alerts: list[Alert]) -> int:
    """
    Sendet mehrere Alerts nacheinander (nicht parallel, wegen Rate-Limits).
    Gibt Anzahl erfolgreich gesendeter Alerts zurück.
    """
    sent = 0
    for alert in alerts:
        if await send_alert(alert):
            sent += 1
        # Kurze Pause zwischen Alerts
        if len(alerts) > 1:
            await asyncio.sleep(1.0)
    return sent


async def send_heartbeat(status: RunStatus) -> None:
    """Sendet ein stilles Status-Update (kein @everyone Ping).

    Die erste Nachricht wird immer editiert statt neu gepostet.
    Die Message-ID wird in der DB unter 'heartbeat_message_id' persistiert.
    """
    cfg = await get_settings(_db)
    if not cfg.discord.status_update:
        return

    embed = _build_heartbeat_embed(status)
    payload = {
        "username": "WSB-Crawler",
        "embeds": [embed],
        # Kein content → kein Ping
    }

    # Gespeicherte Message-ID laden
    message_id: str | None = await _db.get_setting("heartbeat_message_id")

    if message_id:
        # Versuche bestehende Nachricht zu editieren
        edited = await _edit_webhook_message(payload, cfg.discord.webhook_url, message_id)
        if edited:
            logger.debug(f"Heartbeat aktualisiert (message_id={message_id})")
            return
        # Nachricht existiert nicht mehr → neue erstellen
        await _db.set_setting("heartbeat_message_id", "")

    # Erste Nachricht senden und ID speichern
    result = await _send_webhook(payload, cfg.discord.webhook_url, wait=True)
    if result and isinstance(result, str):
        await _db.set_setting("heartbeat_message_id", result)
        logger.info(f"Heartbeat erstellt (message_id={result})")
    else:
        logger.warning("Heartbeat konnte nicht gesendet werden")


async def send_top_tickers(entries: list[TrendEntry], days: int) -> None:
    """Sendet die Top-Ticker-Übersicht als Discord-Embed (für /top Command)."""
    cfg = await get_settings(_db)
    webhook_url = cfg.discord.webhook_url
    if not entries:
        await _send_webhook({"content": f"Keine Daten für die letzten {days} Tage."}, webhook_url)
        return

    lines = []
    for i, entry in enumerate(entries, 1):
        trend = TREND_EMOJI.get(entry.trend_direction.value, "")
        name = entry.company_name or entry.ticker
        price_str = _format_price(entry.current_price) if entry.current_price else "—"
        change_str = _format_change(entry.price_change_period) if entry.price_change_period else "—"
        lines.append(
            f"**{i}.** ${entry.ticker} — {name}\n"
            f"   {trend} {entry.total_mentions} Nennungen | {price_str} ({change_str})"
        )

    embed = {
        "title": f"🏆 Top Ticker — letzte {days} Tage",
        "description": "\n\n".join(lines),
        "color": COLOR_SUCCESS,
        "footer": {"text": "WSB-Crawler v2"},
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    await _send_webhook({"username": "WSB-Crawler", "embeds": [embed]}, webhook_url)
