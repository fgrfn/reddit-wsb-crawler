"""
Telegram-Alert-Kanal (optional, parallel zu Discord).

Sendet Alerts via Telegram Bot API (`sendMessage`) als HTML-formatierte
Nachricht. Aktiv, sobald `telegram_bot_token` **und** `telegram_chat_id`
konfiguriert sind. Async über httpx wie der Rest des Projekts.
"""

from __future__ import annotations

import asyncio
import html

import httpx
from loguru import logger

from wsb_crawler.config import Settings
from wsb_crawler.models import Alert, AlertReason

_API_BASE = "https://api.telegram.org"

_REASON_LABEL = {
    AlertReason.NEW_TICKER: "🆕 Neu im Gespräch",
    AlertReason.SPIKE: "🚀 Stark im Gespräch",
    AlertReason.PRICE_MOVE: "💹 Kurs bewegt sich",
    AlertReason.VELOCITY: "⚡ Frühwarnung",
}
_SENTIMENT_LABEL = {"bullish": "🐂 Positiv", "bearish": "🐻 Negativ", "neutral": "➖ Gemischt"}


def _strength(sentiment: float) -> str:
    """Deutlichkeit der Stimmung in Worten statt als Rohwert."""
    value = abs(sentiment)
    if value >= 0.6:
        return "deutlich"
    if value >= 0.25:
        return "leicht"
    return "knapp"


def _fmt_price(value: float | None, currency: str) -> str:
    if value is None:
        return "—"
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{symbol}{value:,.2f}"


def _fmt_change(pct: float | None) -> str:
    if pct is None:
        return "—"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _build_message(alert: Alert) -> str:
    """Baut eine HTML-Telegram-Nachricht aus einem Alert (spiegelt das Discord-Embed)."""
    spike = alert.spike
    price = spike.price_data
    company = price.company_name if price else None

    header = _REASON_LABEL.get(alert.reason, "⚡ Alert")
    title = f"{header}: <b>${html.escape(alert.ticker)}</b>"
    if company:
        title += f" — {html.escape(company)}"
    lines = [title]

    # Nennungen. Bei der Frühwarnung sind die letzten Läufe die Bezugsgröße —
    # der 30-Tage-Schnitt kann höher liegen und würde der Aussage widersprechen.
    is_velocity = alert.reason == AlertReason.VELOCITY and spike.velocity_avg > 0
    if spike.is_new:
        lines.append(f"📊 <b>{spike.current_mentions}</b> Nennungen · neu")
    elif is_velocity:
        lines.append(
            f"📊 Ø {spike.velocity_avg:.0f} → <b>{spike.current_mentions}</b> Nennungen "
            f"in den letzten Läufen ({spike.velocity_ratio:.1f}× so viele)"
        )
    else:
        lines.append(
            f"📊 <b>{spike.current_mentions}</b> Nennungen — "
            f"{spike.ratio:.1f}× so viele wie sonst (Ø {spike.avg_mentions:.0f})"
        )

    # Stimmung + Engagement
    if spike.signal:
        sig = spike.signal
        mood = _SENTIMENT_LABEL.get(sig.sentiment_label, "➖ Gemischt")
        strength = "" if sig.sentiment_label == "neutral" else f" ({_strength(sig.sentiment)})"
        lines.append(f"🧭 {mood}{strength} · Ø {sig.avg_score:.0f} Upvotes")

    # Kurs
    if price:
        parts = [f"💰 <b>{_fmt_price(price.primary_price, price.currency)}</b>"]
        if price.primary_change is not None:
            parts.append(f"{_fmt_change(price.primary_change)} (24h)")
        if price.change_1h is not None:
            parts.append(f"{_fmt_change(price.change_1h)} (1h)")
        lines.append(" · ".join(parts))

    # News (max. 3)
    for article in spike.news[:3]:
        title_text = html.escape(article.title[:80])
        url = html.escape(article.url, quote=True)
        lines.append(f'📰 <a href="{url}">{title_text}</a>')

    return "\n".join(lines)


async def send_alert(alert: Alert, cfg: Settings, retries: int = 3) -> bool:
    """Sendet einen Alert an Telegram. Gibt True bei Erfolg zurück."""
    tg = cfg.telegram
    if not tg.enabled:
        return False

    url = f"{_API_BASE}/bot{tg.bot_token}/sendMessage"
    payload = {
        "chat_id": tg.chat_id,
        "text": _build_message(alert),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 429:
                    retry_after = float(response.json().get("parameters", {}).get("retry_after", 2))
                    logger.warning(f"Telegram Rate-Limit — warte {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                logger.info(f"Telegram-Alert gesendet: ${alert.ticker}")
                return True
        except Exception as e:
            logger.warning(f"Telegram-Fehler (Versuch {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2**attempt)

    logger.error(f"Telegram-Alert konnte nicht gesendet werden: ${alert.ticker}")
    return False
