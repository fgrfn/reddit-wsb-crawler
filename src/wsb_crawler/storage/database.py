"""
Async SQLite Datenbankschicht via aiosqlite.

Ersetzt die Pickle-Dateien aus v1. Vorteile:
- Daten sind menschenlesbar und querybar
- Kein Versions-Inkompatibilitätsproblem beim Upgrade
- Trend-Analyse direkt per SQL
- Thread-safe (aiosqlite wrapped sqlite3 in einem Thread)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from wsb_crawler.models import (
    Alert,
    RunStatus,
    TickerHistory,
    TrendDirection,
    TrendEntry,
)


@dataclass(frozen=True)
class CachedIsin:
    """Gespeichertes Ergebnis einer ISIN-Suche. `isin=None` = erfolglos gesucht."""

    isin: str | None
    resolved_at: datetime


def _utcnow() -> datetime:
    """Aktuelle Zeit als aware UTC-datetime (ersetzt deprecated datetime.utcnow)."""
    return datetime.now(tz=UTC)


def _parse_dt(value: str) -> datetime:
    """Parst einen ISO-Timestamp aus der DB.

    Alte DB-Einträge sind naive UTC-Strings, neue enthalten +00:00 —
    beide werden einheitlich als aware UTC zurückgegeben.
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


# Schema-Version für Migrationen
SCHEMA_VERSION = 3

# Nachträglich ergänzte Spalten pro Tabelle (Name → SQL-Typ). Werden per
# ALTER TABLE nachgezogen, falls sie in einer bestehenden DB noch fehlen.
_COLUMN_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "alert_history": [
        ("confidence", "INTEGER"),
        ("sentiment", "REAL"),
        ("sentiment_label", "TEXT"),
        ("avg_score", "REAL"),
        # Erfolgskontrolle: Kurs 1 h / 24 h nach dem Alert (NULL = noch nicht gemessen)
        ("price_1h", "REAL"),
        ("price_24h", "REAL"),
    ],
}

# Zeitfenster der Erfolgskontrolle → Spalte. Whitelist, weil der Spaltenname
# in SQL interpoliert wird.
OUTCOME_WINDOWS: dict[int, str] = {1: "price_1h", 24: "price_24h"}

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
    confidence      INTEGER,
    sentiment       REAL,
    sentiment_label TEXT,
    avg_score       REAL,
    price_1h        REAL,
    price_24h       REAL,
    sent_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alert_history(ticker);
CREATE INDEX IF NOT EXISTS idx_alerts_sent ON alert_history(sent_at);

-- Ticker → ISIN. Dauerhafter Cache: eine ISIN ändert sich praktisch nie, also
-- wird pro Ticker genau einmal nachgeschlagen. isin = NULL merkt sich eine
-- erfolglose Suche, damit sie nicht bei jedem Lauf wiederholt wird.
CREATE TABLE IF NOT EXISTS ticker_isin (
    ticker      TEXT PRIMARY KEY,
    isin        TEXT,
    resolved_at TEXT NOT NULL
);
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
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self._path)
        except (OSError, sqlite3.OperationalError) as e:
            raise RuntimeError(
                f"Datenbank konnte nicht geöffnet werden: {self._path.resolve()} ({e}). "
                "Der Prozess muss in ein beschreibbares Verzeichnis geschrieben werden können. "
                "Starte aus einem beschreibbaren Verzeichnis oder setze WSB_DB_PATH auf einen "
                "beschreibbaren absoluten Pfad (z.B. WSB_DB_PATH=~/.local/share/wsb-crawler/wsb.db)."
            ) from e
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(CREATE_TABLES)
        await self._run_column_migrations()
        await self._apply_schema_version()
        logger.info(f"Datenbank initialisiert: {self._path}")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> Database:
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

    async def _run_column_migrations(self) -> None:
        """Ergänzt fehlende Spalten in bestehenden DBs (idempotent via PRAGMA-Check)."""
        added = 0
        for table, columns in _COLUMN_MIGRATIONS.items():
            async with self.conn.execute(f"PRAGMA table_info({table})") as cur:
                existing = {row["name"] for row in await cur.fetchall()}
            for name, sql_type in columns:
                if name not in existing:
                    await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                    added += 1
        if added:
            await self.conn.commit()
            logger.info(f"Schema-Migration: {added} Spalte(n) ergänzt")

    async def _apply_schema_version(self) -> None:
        async with self.conn.execute("SELECT MAX(version) as v FROM schema_version") as cur:
            row = await cur.fetchone()
            current = row["v"] if row and row["v"] else 0

        if current < SCHEMA_VERSION:
            await self.conn.execute(
                "INSERT OR IGNORE INTO schema_version VALUES (?, ?)",
                (SCHEMA_VERSION, _utcnow().isoformat()),
            )
            await self.conn.commit()
            logger.debug(f"Schema auf Version {SCHEMA_VERSION} aktualisiert")

    # ── Crawl Runs ──────────────────────────────────────────────────────────

    async def start_run(self, subreddits: list[str]) -> str:
        """Neuen Crawl-Lauf registrieren, gibt run_id zurück."""
        run_id = str(uuid.uuid4())
        await self.conn.execute(
            """INSERT INTO crawl_runs (id, started_at, subreddits)
               VALUES (?, ?, ?)""",
            (run_id, _utcnow().isoformat(), json.dumps(subreddits)),
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
                _utcnow().isoformat(),
                posts_scanned,
                comments_scanned,
                1 if is_healthy else 0,
                run_id,
            ),
        )
        await self.conn.commit()

    async def save_run_mentions(self, run_id: str, counts: dict[str, int]) -> None:
        """Speichert Ticker-Mention-Counts eines Laufs."""
        now = _utcnow().isoformat()
        await self.conn.executemany(
            "INSERT INTO ticker_mentions (run_id, ticker, mentions, recorded_at) VALUES (?, ?, ?, ?)",
            [(run_id, ticker, count, now) for ticker, count in counts.items()],
        )
        await self.conn.commit()

    # ── Ticker History ───────────────────────────────────────────────────────

    async def get_ticker_history(self, ticker: str, days: int = 30) -> TickerHistory:
        """Gibt die tagesaggregierte Mention-History der letzten N Tage zurück."""
        since = (_utcnow() - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            """SELECT DATE(recorded_at) as day, SUM(mentions) as total
               FROM ticker_mentions
               WHERE ticker = ? AND recorded_at >= ?
               GROUP BY DATE(recorded_at)
               ORDER BY day ASC""",
            (ticker, since),
        ) as cur:
            rows = await cur.fetchall()

        return TickerHistory(
            ticker=ticker,
            mention_counts=[
                (datetime.fromisoformat(r["day"]).replace(tzinfo=UTC), r["total"]) for r in rows
            ],
        )

    async def get_daily_mention_totals(self, days: int = 14) -> list[tuple[datetime, int]]:
        """Tägliche Gesamt-Nennungen über alle Ticker (für den Übersichts-Chart)."""
        since = (_utcnow() - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            """SELECT DATE(recorded_at) as day, SUM(mentions) as total
               FROM ticker_mentions
               WHERE recorded_at >= ?
               GROUP BY DATE(recorded_at)
               ORDER BY day ASC""",
            (since,),
        ) as cur:
            rows = await cur.fetchall()
        return [(datetime.fromisoformat(r["day"]).replace(tzinfo=UTC), r["total"]) for r in rows]

    # ── Daten für den Schwellwert-Simulator ──────────────────────────────────

    async def get_runs_since(self, days: int = 30) -> list[tuple[str, datetime]]:
        """(run_id, started_at) aller abgeschlossenen Läufe im Fenster, älteste zuerst."""
        since = (_utcnow() - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            """SELECT id, started_at FROM crawl_runs
               WHERE started_at >= ? AND finished_at IS NOT NULL
               ORDER BY started_at ASC""",
            (since,),
        ) as cur:
            rows = await cur.fetchall()
        return [(row["id"], _parse_dt(row["started_at"])) for row in rows]

    async def get_candidate_tickers_since(self, days: int, min_mentions: int) -> list[str]:
        """Ticker, die im Fenster mindestens einmal `min_mentions` erreichen.

        Alles darunter kann keinen Alert auslösen — diese Vorauswahl hält die
        Datenmenge der Simulation klein.
        """
        since = (_utcnow() - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            """SELECT DISTINCT ticker FROM ticker_mentions
               WHERE recorded_at >= ? AND mentions >= ?""",
            (since, min_mentions),
        ) as cur:
            rows = await cur.fetchall()
        return [row["ticker"] for row in rows]

    async def get_ticker_mention_history(
        self, tickers: list[str], days: int
    ) -> dict[str, list[tuple[datetime, int]]]:
        """Nennungen je Ticker im Fenster als (recorded_at, mentions)."""
        if not tickers:
            return {}
        since = (_utcnow() - timedelta(days=days)).isoformat()
        placeholders = ",".join("?" * len(tickers))
        async with self.conn.execute(
            f"""SELECT ticker, recorded_at, mentions FROM ticker_mentions
                WHERE recorded_at >= ? AND ticker IN ({placeholders})
                ORDER BY recorded_at ASC""",  # noqa: S608 — nur Platzhalter interpoliert
            (since, *tickers),
        ) as cur:
            rows = await cur.fetchall()
        history: dict[str, list[tuple[datetime, int]]] = {}
        for row in rows:
            history.setdefault(row["ticker"], []).append(
                (_parse_dt(row["recorded_at"]), int(row["mentions"]))
            )
        return history

    async def get_ticker_first_seen(self, tickers: list[str]) -> dict[str, datetime]:
        """Erste je gespeicherte Nennung pro Ticker (für den NEW_TICKER-Fall)."""
        if not tickers:
            return {}
        placeholders = ",".join("?" * len(tickers))
        async with self.conn.execute(
            f"""SELECT ticker, MIN(recorded_at) AS first_seen FROM ticker_mentions
                WHERE ticker IN ({placeholders})
                GROUP BY ticker""",  # noqa: S608 — nur Platzhalter interpoliert
            tuple(tickers),
        ) as cur:
            rows = await cur.fetchall()
        return {row["ticker"]: _parse_dt(row["first_seen"]) for row in rows}

    async def get_run_mentions_map(
        self, tickers: list[str], days: int
    ) -> dict[str, dict[str, int]]:
        """{run_id: {ticker: mentions}} im Fenster, auf die gegebenen Ticker begrenzt."""
        if not tickers:
            return {}
        since = (_utcnow() - timedelta(days=days)).isoformat()
        placeholders = ",".join("?" * len(tickers))
        async with self.conn.execute(
            f"""SELECT run_id, ticker, SUM(mentions) AS mentions FROM ticker_mentions
                WHERE recorded_at >= ? AND ticker IN ({placeholders})
                GROUP BY run_id, ticker""",  # noqa: S608 — nur Platzhalter interpoliert
            (since, *tickers),
        ) as cur:
            rows = await cur.fetchall()
        per_run: dict[str, dict[str, int]] = {}
        for row in rows:
            per_run.setdefault(row["run_id"], {})[row["ticker"]] = int(row["mentions"])
        return per_run

    # ── Erfolgskontrolle von Alerts ──────────────────────────────────────────

    async def get_alerts_awaiting_outcome(
        self, window_hours: int, max_age_days: int = 7, limit: int = 25
    ) -> list[dict[str, Any]]:
        """Alerts, deren Nachmessung für dieses Zeitfenster fällig ist.

        Fällig heißt: das Fenster ist verstrichen, es gibt einen Einstiegskurs
        und der Wert fehlt noch. `max_age_days` begrenzt die Nachlaufzeit, damit
        dauerhaft nicht abrufbare Ticker nicht endlos erneut versucht werden.
        """
        column = OUTCOME_WINDOWS.get(window_hours)
        if column is None:
            raise ValueError(f"Unbekanntes Zeitfenster: {window_hours}")

        due_before = (_utcnow() - timedelta(hours=window_hours)).isoformat()
        not_older_than = (_utcnow() - timedelta(days=max_age_days)).isoformat()
        async with self.conn.execute(
            f"""SELECT id, ticker, price, sent_at FROM alert_history
                WHERE {column} IS NULL
                  AND price IS NOT NULL
                  AND sent_at <= ?
                  AND sent_at >= ?
                ORDER BY sent_at ASC
                LIMIT ?""",  # noqa: S608 — Spaltenname aus Whitelist
            (due_before, not_older_than, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def save_alert_outcome(self, alert_id: int, window_hours: int, price: float) -> None:
        """Speichert den nachgemessenen Kurs für ein Zeitfenster."""
        column = OUTCOME_WINDOWS.get(window_hours)
        if column is None:
            raise ValueError(f"Unbekanntes Zeitfenster: {window_hours}")
        await self.conn.execute(
            f"UPDATE alert_history SET {column} = ? WHERE id = ?",  # noqa: S608 — Whitelist
            (price, alert_id),
        )
        await self.conn.commit()

    async def get_alert_outcome_stats(
        self, days: int = 30, hit_threshold_pct: float = 3.0
    ) -> list[dict[str, Any]]:
        """Trefferquote je Alert-Grund über die nachgemessenen Kurse.

        „Treffer" = Kurs im Zeitfenster um mindestens `hit_threshold_pct`
        gestiegen. Alerts ohne Messung zählen nicht in die Quote (nur in
        `alerts`), damit eine ausstehende Messung sie nicht verwässert.
        """
        since = (_utcnow() - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            """SELECT
                   reason,
                   COUNT(*) AS alerts,
                   COUNT(price_1h) AS measured_1h,
                   COUNT(price_24h) AS measured_24h,
                   AVG(CASE WHEN price_1h IS NOT NULL
                       THEN (price_1h - price) / price * 100 END) AS avg_1h,
                   AVG(CASE WHEN price_24h IS NOT NULL
                       THEN (price_24h - price) / price * 100 END) AS avg_24h,
                   SUM(CASE WHEN price_1h IS NOT NULL
                       AND (price_1h - price) / price * 100 >= ? THEN 1 ELSE 0 END) AS hits_1h,
                   SUM(CASE WHEN price_24h IS NOT NULL
                       AND (price_24h - price) / price * 100 >= ? THEN 1 ELSE 0 END) AS hits_24h
               FROM alert_history
               WHERE sent_at >= ? AND price IS NOT NULL AND price > 0
               GROUP BY reason
               ORDER BY alerts DESC""",
            (hit_threshold_pct, hit_threshold_pct, since),
        ) as cur:
            rows = await cur.fetchall()

        stats: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            for window in ("1h", "24h"):
                measured = data[f"measured_{window}"] or 0
                hits = data[f"hits_{window}"] or 0
                data[f"hit_rate_{window}"] = round(hits / measured * 100, 1) if measured else None
                avg = data[f"avg_{window}"]
                data[f"avg_{window}"] = round(avg, 2) if avg is not None else None
            stats.append(data)
        return stats

    async def get_recent_run_mentions(
        self, ticker: str, runs: int = 3, exclude_run_id: str | None = None
    ) -> list[int]:
        """Nennungen des Tickers in den letzten N abgeschlossenen Läufen (neueste zuerst).

        Läufe ohne Nennung des Tickers liefern 0 — Abwesenheit ist für die
        Beschleunigungsmessung eine echte Null, kein fehlender Wert. Basis für
        die Velocity-Erkennung (Spike im Aufbau).
        """
        async with self.conn.execute(
            """SELECT COALESCE(SUM(m.mentions), 0) AS mentions
               FROM (
                   SELECT id, started_at FROM crawl_runs
                   WHERE id != COALESCE(?, '') AND finished_at IS NOT NULL
                   ORDER BY started_at DESC
                   LIMIT ?
               ) r
               LEFT JOIN ticker_mentions m ON m.run_id = r.id AND m.ticker = ?
               GROUP BY r.id, r.started_at
               ORDER BY r.started_at DESC""",
            (exclude_run_id, runs, ticker),
        ) as cur:
            rows = await cur.fetchall()
        return [int(row["mentions"]) for row in rows]

    async def get_avg_mentions(
        self, ticker: str, days: int = 30, exclude_run_id: str | None = None
    ) -> float:
        """Durchschnittliche Nennungen der letzten N Tage (für Spike-Erkennung).

        exclude_run_id: Lauf der nicht mitzählen soll — der aktuelle Lauf darf
        seinen eigenen Durchschnitt nicht verwässern, sonst erkennt der
        Detector den Spike gegen sich selbst.
        """
        since = (_utcnow() - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            """SELECT AVG(daily_total) as avg FROM (
                   SELECT SUM(mentions) as daily_total
                   FROM ticker_mentions
                   WHERE ticker = ? AND recorded_at >= ?
                     AND run_id != COALESCE(?, '')
                   GROUP BY DATE(recorded_at)
               )""",
            (ticker, since, exclude_run_id),
        ) as cur:
            row = await cur.fetchone()
            return float(row["avg"]) if row and row["avg"] else 0.0

    async def is_known_ticker(self, ticker: str, exclude_run_id: str | None = None) -> bool:
        """Prüft ob ein Ticker bereits in der DB bekannt ist.

        exclude_run_id: Lauf der nicht mitzählen soll (siehe get_avg_mentions).
        """
        async with self.conn.execute(
            "SELECT 1 FROM ticker_mentions WHERE ticker = ? AND run_id != COALESCE(?, '') LIMIT 1",
            (ticker, exclude_run_id),
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
            return _parse_dt(row["cooldown_until"]) > _utcnow()

    async def set_cooldown(self, ticker: str, hours: int) -> None:
        """Setzt oder erneuert den Cooldown für einen Ticker."""
        now = _utcnow()
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
        """Speichert einen gesendeten Alert in der History (inkl. Signal-Werten)."""
        price = alert.spike.price_data
        signal = alert.spike.signal
        await self.conn.execute(
            """INSERT INTO alert_history
               (ticker, reason, mentions, avg_mentions, ratio, price, price_change,
                confidence, sentiment, sentiment_label, avg_score, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                alert.ticker,
                alert.reason.value,
                alert.spike.current_mentions,
                alert.spike.avg_mentions,
                alert.spike.ratio,
                price.primary_price if price else None,
                price.primary_change if price else None,
                alert.spike.confidence or None,
                round(signal.sentiment, 4) if signal else None,
                signal.sentiment_label if signal else None,
                round(signal.avg_score, 2) if signal else None,
                alert.triggered_at.isoformat(),
            ),
        )
        await self.conn.commit()

    # ── Trend-Analyse ────────────────────────────────────────────────────────

    async def get_top_tickers(self, days: int = 7, limit: int = 10) -> list[TrendEntry]:
        """Top-Ticker der letzten N Tage, sortiert nach Gesamtnennungen."""
        since = (_utcnow() - timedelta(days=days)).isoformat()
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
            row = await cur.fetchone()
            total_runs = row["c"] if row else 0

        async with self.conn.execute("SELECT COUNT(*) as c FROM alert_history") as cur:
            row = await cur.fetchone()
            total_alerts = row["c"] if row else 0

        async with self.conn.execute(
            "SELECT COUNT(DISTINCT ticker) as c FROM ticker_mentions"
        ) as cur:
            row = await cur.fetchone()
            tracked = row["c"] if row else 0

        last_at = None
        duration = None
        if last_run:
            last_at = _parse_dt(last_run["started_at"])
            if last_run["finished_at"]:
                finished = _parse_dt(last_run["finished_at"])
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
        async with self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        """Schreibt oder überschreibt einen Konfigurationswert in der DB."""
        await self.conn.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                              updated_at = excluded.updated_at""",
            (key, value, _utcnow().isoformat()),
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

    # ── ISIN-Cache ───────────────────────────────────────────────────────────

    async def get_cached_isin(self, ticker: str, retry_after_days: int = 30) -> CachedIsin | None:
        """Gespeicherte ISIN zu einem Ticker.

        Gibt `None` zurück, wenn nichts gespeichert ist — und ebenso, wenn eine
        *erfolglose* Suche länger als `retry_after_days` zurückliegt, damit ein
        später gelisteter Ticker oder ein damaliger Ausfall der Quelle nicht
        dauerhaft als "gibt es nicht" festgeschrieben bleibt. Ein gefundener
        Eintrag läuft nie ab.
        """
        async with self.conn.execute(
            "SELECT isin, resolved_at FROM ticker_isin WHERE ticker = ?", (ticker,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None

        resolved_at = _parse_dt(row["resolved_at"])
        if row["isin"] is None and _utcnow() - resolved_at > timedelta(days=retry_after_days):
            return None
        return CachedIsin(isin=row["isin"], resolved_at=resolved_at)

    async def save_isin(self, ticker: str, isin: str | None) -> None:
        """Speichert das Ergebnis einer ISIN-Suche (auch das leere)."""
        await self.conn.execute(
            """INSERT INTO ticker_isin (ticker, isin, resolved_at) VALUES (?, ?, ?)
               ON CONFLICT(ticker) DO UPDATE SET isin = excluded.isin,
                                                 resolved_at = excluded.resolved_at""",
            (ticker, isin, _utcnow().isoformat()),
        )
        await self.conn.commit()

    # ── Alert History (API) ───────────────────────────────────────────────────

    async def get_alert_history(
        self, limit: int = 50, ticker: str | None = None
    ) -> list[dict[str, Any]]:
        """Gibt Alert-History als Liste von dicts zurück (für API)."""
        query: str
        params: tuple[Any, ...]
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

    async def get_recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Gibt die letzten Crawl-Runs als Liste von dicts zurück (für API)."""
        async with self.conn.execute(
            "SELECT * FROM crawl_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_run_detail(self, run_id: str) -> dict[str, Any] | None:
        """Gibt einen einzelnen Crawl-Run inklusive Top-Mentions zurück."""
        async with self.conn.execute("SELECT * FROM crawl_runs WHERE id = ?", (run_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return None

        detail = dict(row)
        async with self.conn.execute(
            """SELECT ticker, mentions, recorded_at
               FROM ticker_mentions
               WHERE run_id = ?
               ORDER BY mentions DESC, ticker ASC""",
            (run_id,),
        ) as cur:
            rows = await cur.fetchall()
        detail["mentions"] = [dict(r) for r in rows]
        return detail

    # ── Aufräumen ────────────────────────────────────────────────────────────

    async def purge_old_mentions(self, days: int = 90) -> int:
        """Löscht Ticker-Mentions die älter als N Tage sind.

        Die Tabelle wächst sonst unbegrenzt (jeder Lauf schreibt hunderte
        Zeilen, inkl. False-Positive-Rauschen). Gibt die Anzahl gelöschter
        Zeilen zurück.
        """
        cutoff = (_utcnow() - timedelta(days=days)).isoformat()
        cur = await self.conn.execute(
            "DELETE FROM ticker_mentions WHERE recorded_at < ?", (cutoff,)
        )
        await self.conn.commit()
        return cur.rowcount or 0
