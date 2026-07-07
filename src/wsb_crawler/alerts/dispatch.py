"""
Alert-Dispatch: sendet jeden Alert an alle konfigurierten Kanäle.

Discord (Webhook) ist der Pflicht-Kanal, Telegram optional (aktiv sobald
Token + Chat-ID gesetzt sind). Ein Alert gilt als gesendet (`alert.sent`),
sobald mindestens ein Kanal erfolgreich war — davon hängen Cooldown und
History-Speicherung im Runner ab.
"""

from __future__ import annotations

import asyncio

from wsb_crawler.alerts import discord, telegram
from wsb_crawler.config import Settings
from wsb_crawler.models import Alert


async def send_alerts(alerts: list[Alert], cfg: Settings) -> int:
    """Sendet mehrere Alerts an alle aktiven Kanäle. Gibt die Anzahl gesendeter zurück."""
    sent = 0
    for alert in alerts:
        discord_ok = await discord.send_alert(alert)
        telegram_ok = await telegram.send_alert(alert, cfg) if cfg.telegram.enabled else False

        if discord_ok or telegram_ok:
            alert.sent = True
            sent += 1

        # Kurze Pause zwischen Alerts (Rate-Limits beider Kanäle)
        if len(alerts) > 1:
            await asyncio.sleep(1.0)
    return sent
