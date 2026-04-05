"""
Zentrale Konfiguration — gelesen aus der SQLite-Datenbank.

Kein .env mehr. Alle Werte werden beim ersten Start über das
Web-Dashboard (Setup-Wizard) eingetragen und in der DB gespeichert.

Verwendung:
    from wsb_crawler.config import get_settings
    cfg = await get_settings(db)
    cfg.reddit.client_id
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wsb_crawler.storage.database import Database

# Datenbank-Pfad — einziger Wert der noch "hardcoded" ist
DB_PATH = Path("data/wsb_crawler.db")


@dataclass
class RedditSettings:
    client_id: str
    client_secret: str
    user_agent: str = "python:wsb-crawler:v2.0.0 (by /u/youruser)"


@dataclass
class NewsAPISettings:
    key: str
    lang: str = "en"
    window_hours: int = 48


@dataclass
class DiscordSettings:
    webhook_url: str
    bot_token: str | None = None
    command_channel_id: int | None = None
    status_update: bool = True


@dataclass
class AlertSettings:
    min_abs: int = 20
    min_delta: int = 10
    ratio: float = 2.0
    min_price_move: float = 5.0
    max_per_run: int = 3
    cooldown_h: int = 4


@dataclass
class CrawlerSettings:
    subreddits: list[str] = field(default_factory=lambda: ["wallstreetbets", "wallstreetbetsGER"])
    crawl_interval_minutes: int = 30
    posts_limit: int = 500
    comments_limit: int = 100
    alphavantage_api_key: str | None = None
    db_path: Path = field(default_factory=lambda: DB_PATH)
    log_level: str = "INFO"


@dataclass
class Settings:
    reddit: RedditSettings
    newsapi: NewsAPISettings
    discord: DiscordSettings
    alerts: AlertSettings
    crawler: CrawlerSettings


async def get_settings(db: "Database") -> Settings:
    """
    Liest alle Settings aus der DB und gibt ein Settings-Objekt zurück.
    Wirft RuntimeError wenn Pflichtfelder fehlen (→ Setup-Wizard nötig).
    """
    s = await db.get_all_settings()

    def req(key: str) -> str:
        val = s.get(key)
        if not val:
            raise RuntimeError(
                f"Pflichtfeld '{key}' nicht konfiguriert. "
                "Bitte Setup-Wizard unter http://localhost:8080 ausführen."
            )
        return val

    def opt(key: str, default: str | None = None) -> str | None:
        return s.get(key) or default

    subreddits_raw = opt("subreddits", "wallstreetbets,wallstreetbetsGER") or ""
    subreddits = [r.strip() for r in subreddits_raw.split(",") if r.strip()]

    return Settings(
        reddit=RedditSettings(
            client_id=req("reddit_client_id"),
            client_secret=req("reddit_client_secret"),
            user_agent=opt("reddit_user_agent") or "python:wsb-crawler:v2.0.0 (by /u/youruser)",
        ),
        newsapi=NewsAPISettings(
            key=opt("newsapi_key") or "",
            lang=opt("newsapi_lang") or "en",
            window_hours=int(opt("newsapi_window_hours") or "48"),
        ),
        discord=DiscordSettings(
            webhook_url=req("discord_webhook_url"),
            bot_token=opt("discord_bot_token"),
            command_channel_id=int(s["discord_command_channel_id"])
            if s.get("discord_command_channel_id")
            else None,
            status_update=s.get("discord_status_update", "true").lower() == "true",
        ),
        alerts=AlertSettings(
            min_abs=int(opt("alert_min_abs") or "20"),
            min_delta=int(opt("alert_min_delta") or "10"),
            ratio=float(opt("alert_ratio") or "2.0"),
            min_price_move=float(opt("alert_min_price_move") or "5.0"),
            max_per_run=int(opt("alert_max_per_run") or "3"),
            cooldown_h=int(opt("alert_cooldown_h") or "4"),
        ),
        crawler=CrawlerSettings(
            subreddits=subreddits,
            crawl_interval_minutes=int(opt("crawl_interval_minutes") or "30"),
            posts_limit=int(opt("posts_limit") or "500"),
            comments_limit=int(opt("comments_limit") or "100"),
            alphavantage_api_key=opt("alphavantage_api_key"),
            db_path=DB_PATH,
            log_level=opt("log_level") or "INFO",
        ),
    )


    reddit: RedditSettings = Field(default_factory=RedditSettings)
    newsapi: NewsAPISettings = Field(default_factory=NewsAPISettings)
    discord: DiscordSettings = Field(default_factory=DiscordSettings)
    alerts: AlertSettings = Field(default_factory=AlertSettings)
    crawler: CrawlerSettings = Field(default_factory=CrawlerSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Gibt die globale Settings-Instanz zurück (Singleton via lru_cache).

    Beim ersten Aufruf werden alle Werte aus .env geladen und validiert.
    Bei Fehlern (fehlende Pflichtfelder, falsche Typen) wird sofort
    eine ValidationError geworfen — nicht erst beim ersten API-Call.

    Beispiel:
        from wsb_crawler.config import get_settings
        cfg = get_settings()
        print(cfg.crawler.subreddits)
    """
    return Settings()
