"""
Config-Router: GET und PUT für alle Konfigurationseinstellungen.

Achtung: Die API hat keine Authentifizierung — deshalb bindet der Server
per Default nur auf localhost und Secrets werden in GET-Responses maskiert.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from wsb_crawler.__version__ import __version__
from wsb_crawler.alerts.discord import _send_webhook
from wsb_crawler.config import get_settings, is_configured
from wsb_crawler.storage.database import Database

router = APIRouter(tags=["config"])
db: Database = None  # type: ignore[assignment]  # wird in server.py::set_database gesetzt

MASK = "••••••••"

# Werte die nie im Klartext zurückgegeben werden. Die Webhook-URL gehört
# dazu: wer sie kennt, kann beliebige Nachrichten in den Channel posten.
SECRET_KEYS = (
    "reddit_client_secret",
    "reddit_password",
    "newsapi_key",
    "discord_bot_token",
    "discord_webhook_url",
    "telegram_bot_token",
    "alphavantage_api_key",
)


class ConfigPayload(BaseModel):
    """Alle konfigurierbaren Felder. None-Werte werden ignoriert."""

    # Reddit (Pflicht)
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str | None = None
    reddit_username: str | None = None
    reddit_password: str | None = None

    # NewsAPI (optional)
    newsapi_key: str | None = None
    newsapi_lang: str | None = None
    newsapi_window_hours: int | None = Field(default=None, ge=1, le=168)

    # Discord (Pflicht)
    discord_webhook_url: str | None = None
    discord_bot_token: str | None = None
    discord_command_channel_id: str | None = None
    discord_status_update: str | None = None

    # Telegram (optional)
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # Alert-Schwellwerte
    alert_min_abs: int | None = Field(default=None, ge=1)
    alert_min_delta: int | None = Field(default=None, ge=0)
    alert_ratio: float | None = Field(default=None, gt=0)
    alert_min_price_move: float | None = Field(default=None, ge=0)
    alert_max_per_run: int | None = Field(default=None, ge=1, le=25)
    alert_cooldown_h: int | None = Field(default=None, ge=0)

    # Crawler
    subreddits: str | None = None  # komma-separiert
    crawl_interval_minutes: int | None = Field(default=None, ge=1)
    schedule_mode: str | None = None  # "interval" oder "cron"
    cron_expression: str | None = None  # 5-Feld-Cron
    posts_limit: int | None = Field(default=None, ge=1, le=1000)
    comments_limit: int | None = Field(default=None, ge=0, le=500)
    log_level: str | None = None
    alphavantage_api_key: str | None = None

    @field_validator("discord_webhook_url")
    @classmethod
    def validate_webhook(cls, v: str | None) -> str | None:
        if v and not v.startswith("https://discord.com/api/webhooks/"):
            raise ValueError("Webhook-URL muss mit https://discord.com/api/webhooks/ beginnen")
        return v

    @field_validator("schedule_mode")
    @classmethod
    def validate_schedule_mode(cls, v: str | None) -> str | None:
        if v and v not in ("interval", "cron"):
            raise ValueError("schedule_mode muss 'interval' oder 'cron' sein")
        return v

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v: str | None) -> str | None:
        if v and v.strip():
            from wsb_crawler.cron import validate_cron

            try:
                validate_cron(v.strip())
            except ValueError as exc:
                raise ValueError(f"Ungültiger Cron-Ausdruck: {exc}") from exc
        return v


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """Gibt alle gespeicherten Settings zurück. Secrets werden maskiert."""
    settings = await db.get_all_settings()
    # Secrets maskieren (nicht komplett entfernen, damit UI weiß ob gesetzt)
    for secret_key in SECRET_KEYS:
        if settings.get(secret_key):
            settings[secret_key] = MASK
    return settings


@router.put("/config")
async def update_config(payload: ConfigPayload) -> dict[str, Any]:
    """Speichert geänderte Settings in der DB."""
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Keine Werte zum Speichern")

    # Maskierte Platzhalter-Werte niemals überschreiben
    data = {k: v for k, v in data.items() if str(v) != MASK}
    if not data:
        return {"ok": True, "updated": []}

    for key, value in data.items():
        # Führende/nachfolgende Whitespace-Zeichen entfernen (verhindert Copy-Paste-Fehler)
        await db.set_setting(key, str(value).strip())

    return {"ok": True, "updated": list(data.keys())}


@router.get("/config/status")
async def config_status() -> dict[str, Any]:
    """Gibt zurück ob das System vollständig konfiguriert ist."""
    configured = await is_configured(db)
    return {"configured": configured}


@router.post("/config/discord/test")
async def test_discord_webhook() -> dict[str, Any]:
    """Sendet eine Testnachricht an den gespeicherten Discord-Webhook."""
    if not await is_configured(db):
        raise HTTPException(status_code=400, detail="Konfiguration unvollständig")

    cfg = await get_settings(db)
    payload = {
        "username": "WSB-Crawler",
        "embeds": [
            {
                "title": "WSB-Crawler Test",
                "description": "Discord-Benachrichtigung funktioniert.",
                "color": 0x57F287,
                "footer": {"text": f"WSB-Crawler v{__version__} • Testnachricht"},
            }
        ],
    }
    if not await _send_webhook(payload, cfg.discord.webhook_url):
        raise HTTPException(
            status_code=502, detail="Discord-Testnachricht konnte nicht gesendet werden"
        )
    return {"ok": True}
