"""
Zentrale Datenmodelle für den WSB-Crawler.

Alle Strukturen sind typisierte Dataclasses (oder Pydantic-Models wo
Validierung gebraucht wird). Kein dict-Herumreichen mehr.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────────────


class AlertReason(str, Enum):
    """Warum wurde ein Alert ausgelöst?"""

    NEW_TICKER = "new_ticker"          # Ticker noch nie gesehen, hohe abs. Nennungen
    SPIKE = "spike"                    # Bekannter Ticker, plötzlicher Anstieg
    PRICE_MOVE = "price_move"          # Signifikante Kursbewegung + Nennungen


class MarketStatus(str, Enum):
    PRE_MARKET = "pre_market"
    OPEN = "open"
    AFTER_HOURS = "after_hours"
    CLOSED = "closed"


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


# ── Reddit ─────────────────────────────────────────────────────────────────


@dataclass
class RedditPost:
    """Ein einzelner Reddit-Post oder Kommentar."""

    id: str
    subreddit: str
    title: str
    text: str
    author: str
    score: int
    upvote_ratio: float
    created_utc: datetime
    url: str
    is_comment: bool = False
    parent_id: str | None = None


@dataclass
class TickerMention:
    """Eine erkannte Ticker-Erwähnung in einem Post/Kommentar."""

    ticker: str
    post_id: str
    subreddit: str
    context: str          # ~100 Zeichen rund um den Ticker im Text
    score: int            # Post-Score → gewichtet spätere Analyse
    created_utc: datetime


# ── Crawl-Ergebnis ─────────────────────────────────────────────────────────


@dataclass
class CrawlResult:
    """Aggregiertes Ergebnis eines einzelnen Crawl-Laufs."""

    run_id: str                    # UUID, eindeutig pro Lauf
    started_at: datetime
    finished_at: datetime | None = None

    subreddits: list[str] = field(default_factory=list)
    posts_scanned: int = 0
    comments_scanned: int = 0

    # ticker → Anzahl Nennungen in diesem Lauf
    mention_counts: dict[str, int] = field(default_factory=dict)

    # Alle Einzelnennungen (für DB-Speicherung)
    mentions: list[TickerMention] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def top_tickers(self) -> list[tuple[str, int]]:
        """Gibt die Ticker sortiert nach Nennungen zurück."""
        return sorted(self.mention_counts.items(), key=lambda x: x[1], reverse=True)


# ── Finanzdaten ────────────────────────────────────────────────────────────


@dataclass
class PriceData:
    """Aktueller Kurs + Veränderungen für einen Ticker."""

    ticker: str
    company_name: str | None

    price: float | None
    currency: str = "USD"

    change_1h: float | None = None    # % Veränderung letzte Stunde
    change_24h: float | None = None   # % Veränderung letzte 24h
    change_7d: float | None = None    # % Veränderung letzte 7 Tage

    pre_market_price: float | None = None
    pre_market_change: float | None = None

    after_hours_price: float | None = None
    after_hours_change: float | None = None

    market_status: MarketStatus = MarketStatus.CLOSED
    volume: int | None = None
    market_cap: float | None = None

    fetched_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def primary_price(self) -> float | None:
        """Gibt den relevantesten Kurs zurück (Pre/After/Regular)."""
        if self.market_status == MarketStatus.PRE_MARKET and self.pre_market_price:
            return self.pre_market_price
        if self.market_status == MarketStatus.AFTER_HOURS and self.after_hours_price:
            return self.after_hours_price
        return self.price

    @property
    def primary_change(self) -> float | None:
        """Gibt die relevanteste Kursveränderung zurück."""
        if self.market_status == MarketStatus.PRE_MARKET:
            return self.pre_market_change or self.change_24h
        if self.market_status == MarketStatus.AFTER_HOURS:
            return self.after_hours_change or self.change_24h
        return self.change_24h


# ── News ───────────────────────────────────────────────────────────────────


@dataclass
class NewsArticle:
    """Eine News-Headline zu einem Ticker."""

    ticker: str
    title: str
    source: str
    url: str
    published_at: datetime
    sentiment: float | None = None    # -1.0 bis 1.0, optional


# ── Analyse ────────────────────────────────────────────────────────────────


@dataclass
class TickerHistory:
    """Historische Daten eines Tickers aus der DB."""

    ticker: str
    mention_counts: list[tuple[datetime, int]]   # (timestamp, count)

    @property
    def avg_mentions(self) -> float:
        if not self.mention_counts:
            return 0.0
        return sum(c for _, c in self.mention_counts) / len(self.mention_counts)

    @property
    def trend_direction(self) -> TrendDirection:
        if len(self.mention_counts) < 2:
            return TrendDirection.FLAT
        recent = sum(c for _, c in self.mention_counts[-3:]) / 3
        older = sum(c for _, c in self.mention_counts[-7:-3]) / 4
        if older == 0:
            return TrendDirection.FLAT
        delta = (recent - older) / older
        if delta > 0.2:
            return TrendDirection.UP
        if delta < -0.2:
            return TrendDirection.DOWN
        return TrendDirection.FLAT


@dataclass
class SpikeResult:
    """Ergebnis der Spike-Analyse für einen einzelnen Ticker."""

    ticker: str
    current_mentions: int
    avg_mentions: float           # Historischer Durchschnitt (letzte 30 Tage)
    ratio: float                  # current / avg
    delta: int                    # current - avg (absolut)
    is_new: bool                  # Ticker noch nie gesehen?
    reason: AlertReason | None    # None = kein Alert
    price_data: PriceData | None = None
    news: list[NewsArticle] = field(default_factory=list)
    history: TickerHistory | None = None


# ── Alerts ─────────────────────────────────────────────────────────────────


@dataclass
class Alert:
    """Ein ausgelöster Alert, bereit zum Versenden."""

    ticker: str
    reason: AlertReason
    spike: SpikeResult

    triggered_at: datetime = field(default_factory=datetime.utcnow)
    sent: bool = False
    cooldown_until: datetime | None = None


# ── Trend-Analyse (für /top und /chart) ────────────────────────────────────


@dataclass
class TrendEntry:
    """Ein Eintrag in der Trend-Übersicht."""

    ticker: str
    company_name: str | None
    total_mentions: int
    avg_daily_mentions: float
    peak_day: datetime | None
    peak_mentions: int
    trend_direction: TrendDirection
    current_price: float | None = None
    price_change_period: float | None = None   # % Veränderung im Zeitraum


@dataclass
class RunStatus:
    """Aktueller Status des Crawlers (für /status Command)."""

    last_run_at: datetime | None
    last_run_duration_seconds: float | None
    total_runs: int
    total_alerts_sent: int
    tracked_tickers: int
    next_run_at: datetime | None
    is_healthy: bool
