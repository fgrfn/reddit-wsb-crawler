"""
Config-Router: GET und PUT für alle Konfigurationseinstellungen.
Kein Auth nötig — läuft nur auf localhost.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from wsb_crawler.storage.database import Database

router = APIRouter(tags=["config"])
db: Database  # wird in server.py gesetzt


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
    newsapi_window_hours: int | None = None

    # Discord (Pflicht)
    discord_webhook_url: str | None = None
    discord_bot_token: str | None = None
    discord_command_channel_id: str | None = None
    discord_status_update: str | None = None

    # Alert-Schwellwerte
    alert_min_abs: int | None = None
    alert_min_delta: int | None = None
    alert_ratio: float | None = None
    alert_min_price_move: float | None = None
    alert_max_per_run: int | None = None
    alert_cooldown_h: int | None = None

    # Crawler
    subreddits: str | None = None          # komma-separiert
    crawl_interval_minutes: int | None = None
    posts_limit: int | None = None
    comments_limit: int | None = None
    log_level: str | None = None
    alphavantage_api_key: str | None = None

    @field_validator("discord_webhook_url")
    @classmethod
    def validate_webhook(cls, v: str | None) -> str | None:
        if v and not v.startswith("https://discord.com/api/webhooks/"):
            raise ValueError("Webhook-URL muss mit https://discord.com/api/webhooks/ beginnen")
        return v


@router.get("/config")
async def get_config() -> dict:
    """Gibt alle gespeicherten Settings zurück. Secrets werden maskiert."""
    settings = await db.get_all_settings()
    # Secrets maskieren (nicht komplett entfernen, damit UI weiß ob gesetzt)
    for secret_key in (
        "reddit_client_secret", "reddit_password",
        "newsapi_key", "discord_bot_token", "alphavantage_api_key",
    ):
        if settings.get(secret_key):
            settings[secret_key] = "••••••••"
    return settings


@router.put("/config")
async def update_config(payload: ConfigPayload) -> dict:
    """Speichert geänderte Settings in der DB."""
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Keine Werte zum Speichern")

    # Maskierte Platzhalter-Werte niemals überschreiben
    data = {k: v for k, v in data.items() if str(v) != "••••••••"}
    if not data:
        return {"ok": True, "updated": []}

    for key, value in data.items():
        # Führende/nachfolgende Whitespace-Zeichen entfernen (verhindert Copy-Paste-Fehler)
        await db.set_setting(key, str(value).strip())

    return {"ok": True, "updated": list(data.keys())}


@router.get("/config/status")
async def config_status() -> dict:
    """Gibt zurück ob das System vollständig konfiguriert ist."""
    configured = await db.is_configured()
    return {"configured": configured}
