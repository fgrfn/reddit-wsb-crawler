"""
Async SQLite Datenbankschicht via aiosqlite.

Ersetzt die Pickle-Dateien aus v1. Vorteile:
- Daten sind menschenlesbar und querybar
- Kein Versions-Inkompatibilitätsproblem beim Upgrade
- Trend-Analyse direkt per SQL
- Thread-safe (aiosqlite wrapped sqlite3 in einem Thread)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
from loguru import logger

from wsb_crawler.models import (
    Alert,
    RunStatus,
    TickerHistory,
    TrendDirection,
    TrendEntry,
)

# Schema-Version für spätere Migrationen
SCHEMA_VERSION = 1

CREATE_TABLES = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

-- Schlüssel-Wert-Store für alle Konfigurationseinstellungen
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Jeder Crawl-Lauf
CREATE TABLE IF NOT EXISTS crawl_runs (
    id                  TEXT PRIMARY KEY,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    posts_scanned       INTEGER DEFAULT 0,
    comments_scanned    INTEGER DEFAULT 0,
    subreddits          TEXT NOT NULL,   -- JSON-Array
    is_healthy          INTEGER DEFAULT 1
);

-- Ticker-Nennungen pro Lauf (aggregiert)
CREATE TABLE IF NOT EXISTS ticker_mentions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES crawl_runs(id),
    ticker      TEXT NOT NULL,
    mentions    INTEGER NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mentions_ticker ON ticker_mentions(ticker);
CREATE INDEX IF NOT EXISTS idx_mentions_recorded ON ticker_mentions(recorded_at);

-- Cooldown-Tracking: wann wurde zuletzt ein Alert für einen Ticker gesendet?
CREATE TABLE IF NOT EXISTS alert_cooldowns (
    ticker          TEXT PRIMARY KEY,
    last_alert_at   TEXT NOT NULL,
    cooldown_until  TEXT NOT NULL,
    alert_count     INTEGER DEFAULT 1
);

-- Alert-History für Analyse
CREATE TABLE IF NOT EXISTS alert_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    reason          TEXT NOT NULL,
    mentions        INTEGER NOT NULL,
    avg_mentions    REAL NOT NULL,
    ratio           REAL NOT NULL,
    price           REAL,
    price_change    REAL,
    sent_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alert_history(ticker);
CREATE INDEX IF NOT EXISTS idx_alerts_sent ON alert_history(sent_at);
"""


class Database:
    """
    Hauptklasse für alle DB-Operationen.

    Verwendung:
        db = Database(Path("data/wsb.db"))
        await db.init()

        # oder als Context Manager:
        async with Database(path) as db:
            await db.save_run_mentions(run_id, counts)
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Verbindung öffnen + Schema anlegen."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(CREATE_TABLES)
        await self._apply_schema_version()
        logger.info(f"Datenbank initialisiert: {self._path}")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "Database":
        await self.init()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Datenbank nicht initialisiert. Bitte zuerst init() aufrufen.")
        return self._conn

    # ── Schema ──────────────────────────────────────────────────────────────

    async def _apply_schema_version(self) -> None:
        async with self.conn.execute("SELECT MAX(version) as v FROM schema_version") as cur:
            row = await cur.fetchone()
            current = row["v"] if row and row["v"] else 0

        if current < SCHEMA_VERSION:
            await self.conn.execute(
                "INSERT OR IGNORE INTO schema_version VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.utcnow().isoformat()),
            )
            await self.conn.commit()
            logger.debug(f"Schema auf Version {SCHEMA_VERSION} aktualisiert")

    # ── Crawl Runs ──────────────────────────────────────────────────────────

    async def start_run(self, subreddits: list[str]) -> str:
        """Neuen Crawl-Lauf registrieren, gibt run_id zurück."""
        import json
        run_id = str(uuid.uuid4())
        await self.conn.execute(
            """INSERT INTO crawl_runs (id, started_at, subreddits)
               VALUES (?, ?, ?)""",
            (run_id, datetime.utcnow().isoformat(), json.dumps(subreddits)),
        )
        await self.conn.commit()
        return run_id

    async def finish_run(
        self,
        run_id: str,
        posts_scanned: int,
        comments_scanned: int,
        is_healthy: bool = True,
    ) -> None:
        await self.conn.execute(
            """UPDATE crawl_runs
               SET finished_at=?, posts_scanned=?, comments_scanned=?, is_healthy=?
               WHERE id=?""",
            (
                datetime.utcnow().isoformat(),
                posts_scanned,
                comments_scanned,
                1 if is_healthy else 0,
                run_id,
            ),
        )
        await self.conn.commit()

    async def save_run_mentions(self, run_id: str, counts: dict[str, int]) -> None:
        """Speichert Ticker-Mention-Counts eines Laufs."""
        now = datetime.utcnow().isoformat()
        await self.conn.executemany(
            "INSERT INTO ticker_mentions (run_id, ticker, mentions, recorded_at) VALUES (?, ?, ?, ?)",
            [(run_id, ticker, count, now) for ticker, count in counts.items()],
        )
        await self.conn.commit()

    # ── Ticker History ───────────────────────────────────────────────────────

    async def get_ticker_history(self, ticker: str, days: int = 30) -> TickerHistory:
        """Gibt die Mention-History der letzten N Tage zurück."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            """SELECT recorded_at, SUM(mentions) as total
               FROM ticker_mentions
               WHERE ticker = ? AND recorded_at >= ?
               GROUP BY DATE(recorded_at)
               ORDER BY recorded_at ASC""",
            (ticker, since),
        ) as cur:
            rows = await cur.fetchall()

        return TickerHistory(
            ticker=ticker,
            mention_counts=[
                (datetime.fromisoformat(r["recorded_at"]), r["total"])
                for r in rows
            ],
        )

    async def get_avg_mentions(self, ticker: str, days: int = 30) -> float:
        """Durchschnittliche Nennungen der letzten N Tage (für Spike-Erkennung)."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            """SELECT AVG(daily_total) as avg FROM (
                   SELECT SUM(mentions) as daily_total
                   FROM ticker_mentions
                   WHERE ticker = ? AND recorded_at >= ?
                   GROUP BY DATE(recorded_at)
               )""",
            (ticker, since),
        ) as cur:
            row = await cur.fetchone()
            return float(row["avg"]) if row and row["avg"] else 0.0

    async def is_known_ticker(self, ticker: str) -> bool:
        """Prüft ob ein Ticker bereits in der DB bekannt ist."""
        async with self.conn.execute(
            "SELECT 1 FROM ticker_mentions WHERE ticker = ? LIMIT 1", (ticker,)
        ) as cur:
            return await cur.fetchone() is not None

    # ── Cooldowns ────────────────────────────────────────────────────────────

    async def is_on_cooldown(self, ticker: str) -> bool:
        """Gibt True zurück wenn der Ticker aktuell im Cooldown ist."""
        async with self.conn.execute(
            "SELECT cooldown_until FROM alert_cooldowns WHERE ticker = ?", (ticker,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return False
            return datetime.fromisoformat(row["cooldown_until"]) > datetime.utcnow()

    async def set_cooldown(self, ticker: str, hours: int) -> None:
        """Setzt oder erneuert den Cooldown für einen Ticker."""
        now = datetime.utcnow()
        cooldown_until = (now + timedelta(hours=hours)).isoformat()
        await self.conn.execute(
            """INSERT INTO alert_cooldowns (ticker, last_alert_at, cooldown_until, alert_count)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(ticker) DO UPDATE SET
                   last_alert_at = excluded.last_alert_at,
                   cooldown_until = excluded.cooldown_until,
                   alert_count = alert_count + 1""",
            (ticker, now.isoformat(), cooldown_until),
        )
        await self.conn.commit()

    # ── Alert History ────────────────────────────────────────────────────────

    async def save_alert(self, alert: Alert) -> None:
        """Speichert einen gesendeten Alert in der History."""
        price = alert.spike.price_data
        await self.conn.execute(
            """INSERT INTO alert_history
               (ticker, reason, mentions, avg_mentions, ratio, price, price_change, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                alert.ticker,
                alert.reason.value,
                alert.spike.current_mentions,
                alert.spike.avg_mentions,
                alert.spike.ratio,
                price.primary_price if price else None,
                price.primary_change if price else None,
                alert.triggered_at.isoformat(),
            ),
        )
        await self.conn.commit()

    # ── Trend-Analyse ────────────────────────────────────────────────────────

    async def get_top_tickers(self, days: int = 7, limit: int = 10) -> list[TrendEntry]:
        """Top-Ticker der letzten N Tage, sortiert nach Gesamtnennungen."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            """SELECT
                   ticker,
                   SUM(daily_sum)  AS total,
                   AVG(daily_sum)  AS avg_daily,
                   MAX(daily_sum)  AS peak,
                   (SELECT DATE(tm2.recorded_at)
                    FROM ticker_mentions tm2
                    WHERE tm2.ticker = daily.ticker
                      AND tm2.recorded_at >= ?
                    GROUP BY DATE(tm2.recorded_at)
                    ORDER BY SUM(tm2.mentions) DESC
                    LIMIT 1)        AS peak_day
               FROM (
                   SELECT ticker, DATE(recorded_at) AS recorded_at,
                          SUM(mentions) AS daily_sum
                   FROM ticker_mentions
                   WHERE recorded_at >= ?
                   GROUP BY ticker, DATE(recorded_at)
               ) AS daily
               GROUP BY ticker
               ORDER BY total DESC
               LIMIT ?""",
            (since, since, limit),
        ) as cur:
            rows = await cur.fetchall()

        return [
            TrendEntry(
                ticker=r["ticker"],
                company_name=None,  # wird vom Resolver nachträglich befüllt
                total_mentions=r["total"],
                avg_daily_mentions=r["avg_daily"] or 0.0,
                peak_day=datetime.fromisoformat(r["peak_day"]) if r["peak_day"] else None,
                peak_mentions=r["peak"] or 0,
                trend_direction=TrendDirection.FLAT,  # wird von trends.py gesetzt
            )
            for r in rows
        ]

    # ── Status ───────────────────────────────────────────────────────────────

    async def get_run_status(self) -> RunStatus:
        """Aktueller Crawler-Status für /status Command."""
        async with self.conn.execute(
            "SELECT started_at, finished_at FROM crawl_runs ORDER BY started_at DESC LIMIT 1"
        ) as cur:
            last_run = await cur.fetchone()

        async with self.conn.execute("SELECT COUNT(*) as c FROM crawl_runs") as cur:
            total_runs = (await cur.fetchone())["c"]  # type: ignore[index]

        async with self.conn.execute("SELECT COUNT(*) as c FROM alert_history") as cur:
            total_alerts = (await cur.fetchone())["c"]  # type: ignore[index]

        async with self.conn.execute(
            "SELECT COUNT(DISTINCT ticker) as c FROM ticker_mentions"
        ) as cur:
            tracked = (await cur.fetchone())["c"]  # type: ignore[index]

        last_at = None
        duration = None
        if last_run:
            last_at = datetime.fromisoformat(last_run["started_at"])
            if last_run["finished_at"]:
                finished = datetime.fromisoformat(last_run["finished_at"])
                duration = (finished - last_at).total_seconds()

        return RunStatus(
            last_run_at=last_at,
            last_run_duration_seconds=duration,
            total_runs=total_runs,
            total_alerts_sent=total_alerts,
            tracked_tickers=tracked,
            next_run_at=None,  # wird vom Scheduler gesetzt
            is_healthy=True,
        )

    # ── Settings ─────────────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> str | None:
        """Liest einen einzelnen Konfigurationswert aus der DB."""
        async with self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        """Schreibt oder überschreibt einen Konfigurationswert in der DB."""
        await self.conn.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                              updated_at = excluded.updated_at""",
            (key, value, datetime.utcnow().isoformat()),
        )
        await self.conn.commit()

    async def get_all_settings(self) -> dict[str, str]:
        """Gibt alle gespeicherten Settings als dict zurück."""
        async with self.conn.execute("SELECT key, value FROM settings") as cur:
            rows = await cur.fetchall()
        return {r["key"]: r["value"] for r in rows}

    async def is_configured(self) -> bool:
        """True wenn Mindest-Konfiguration (Reddit + Discord) vorhanden ist."""
        required = ["reddit_client_id", "reddit_client_secret", "discord_webhook_url"]
        for key in required:
            val = await self.get_setting(key)
            if not val:
                return False
        return True

    # ── Alert History (API) ───────────────────────────────────────────────────

    async def get_alert_history(
        self, limit: int = 50, ticker: str | None = None
    ) -> list[dict]:
        """Gibt Alert-History als Liste von dicts zurück (für API)."""
        if ticker:
            query = """SELECT * FROM alert_history WHERE ticker = ?
                       ORDER BY sent_at DESC LIMIT ?"""
            params = (ticker.upper(), limit)
        else:
            query = "SELECT * FROM alert_history ORDER BY sent_at DESC LIMIT ?"
            params = (limit,)

        async with self.conn.execute(query, params) as cur:
            rows = await cur.fetchall()

        return [dict(r) for r in rows]

    async def get_recent_runs(self, limit: int = 20) -> list[dict]:
        """Gibt die letzten Crawl-Runs als Liste von dicts zurück (für API)."""
        async with self.conn.execute(
            "SELECT * FROM crawl_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
