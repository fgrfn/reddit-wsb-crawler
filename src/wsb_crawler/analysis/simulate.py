"""
Schwellwert-Simulator: spielt gespeicherte Historie mit anderen Schwellwerten
durch.

Beantwortet „was hätte Faktor 1.8 in den letzten 30 Tagen ausgelöst?", ohne Tage
zu warten. Grundlage sind die gespeicherten `ticker_mentions` pro Lauf.

Bewusste Grenzen (die Simulation ist eine Näherung, keine Wiederholung):
- Kurs- und News-Anreicherung wird nicht simuliert, also entsteht auch kein
  PRICE_MOVE — solche Alerts erscheinen hier als SPIKE.
- Cooldown und `max_per_run` werden angewandt, aber ohne die echte
  Reihenfolge-Historie; die Zahlen sind Näherungen nach oben.
- Nur Ticker, die im Fenster mindestens einmal die Mindestschwelle erreichen,
  werden geladen — darunter kann ohnehin nichts auslösen.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from wsb_crawler.analysis.detector import compute_velocity
from wsb_crawler.models import AlertReason

if TYPE_CHECKING:
    from wsb_crawler.storage.database import Database

# Basislinie des Detectors: Tagesschnitt der letzten 30 Tage
BASELINE_DAYS = 30


@dataclass
class SimulationThresholds:
    """Schwellwerte, die durchgespielt werden sollen."""

    min_abs: int = 20
    min_delta: int = 10
    ratio: float = 2.0
    max_per_run: int = 3
    cooldown_h: int = 4
    velocity_enabled: bool = True
    velocity_ratio: float = 2.5
    velocity_min_abs: int = 8
    velocity_runs: int = 3

    @property
    def min_relevant(self) -> int:
        floor = min(self.min_abs, self.min_delta)
        if self.velocity_enabled:
            floor = min(floor, self.velocity_min_abs)
        return max(1, floor)


@dataclass
class SimulationResult:
    days: int
    runs_evaluated: int
    total_alerts: int = 0
    per_reason: dict[str, int] = field(default_factory=dict)
    per_ticker: dict[str, int] = field(default_factory=dict)
    suppressed_by_cooldown: int = 0
    suppressed_by_cap: int = 0

    @property
    def alerts_per_day(self) -> float:
        return round(self.total_alerts / self.days, 2) if self.days else 0.0

    def as_dict(self) -> dict[str, Any]:
        top = sorted(self.per_ticker.items(), key=lambda kv: kv[1], reverse=True)[:10]
        return {
            "days": self.days,
            "runs_evaluated": self.runs_evaluated,
            "total_alerts": self.total_alerts,
            "alerts_per_day": self.alerts_per_day,
            "per_reason": self.per_reason,
            "suppressed_by_cooldown": self.suppressed_by_cooldown,
            "suppressed_by_cap": self.suppressed_by_cap,
            "top_tickers": [{"ticker": t, "alerts": n} for t, n in top],
        }


def _daily_average(
    history: list[tuple[datetime, int]], before: datetime, days: int = BASELINE_DAYS
) -> float:
    """Tagesschnitt der Nennungen in den `days` Tagen vor `before`.

    Spiegelt `Database.get_avg_mentions`: pro Tag summieren, dann über die Tage
    mit Daten mitteln.
    """
    window_start = before - timedelta(days=days)
    per_day: dict[str, int] = defaultdict(int)
    for recorded_at, mentions in history:
        if window_start <= recorded_at < before:
            per_day[recorded_at.date().isoformat()] += mentions
    if not per_day:
        return 0.0
    return sum(per_day.values()) / len(per_day)


async def simulate_thresholds(
    db: Database, thresholds: SimulationThresholds, days: int = 30
) -> SimulationResult:
    """Spielt die gespeicherte Historie mit den gegebenen Schwellwerten durch."""
    runs = await db.get_runs_since(days=days)
    result = SimulationResult(days=days, runs_evaluated=len(runs))
    if not runs:
        return result

    # Nur Ticker laden, die im Fenster überhaupt die Mindestschwelle erreichen
    candidates = await db.get_candidate_tickers_since(
        days=days, min_mentions=thresholds.min_relevant
    )
    if not candidates:
        return result

    # Historie dieser Ticker inkl. Vorlauf für die Basislinie
    history = await db.get_ticker_mention_history(candidates, days=days + BASELINE_DAYS)
    first_seen = await db.get_ticker_first_seen(candidates)
    per_run = await db.get_run_mentions_map(candidates, days=days)

    cooldown_until: dict[str, datetime] = {}

    for run_id, started_at in runs:
        mentions = per_run.get(run_id, {})
        if not mentions:
            continue

        run_hits: list[tuple[float, str, AlertReason]] = []
        for ticker, current in mentions.items():
            if current < thresholds.min_relevant:
                continue

            avg = _daily_average(history.get(ticker, []), before=started_at)
            is_new = first_seen.get(ticker, started_at) >= started_at
            ratio = current / avg if avg > 0 else float("inf")
            delta = current - int(avg)

            reason: AlertReason | None = None
            if is_new and current >= thresholds.min_abs:
                reason = AlertReason.NEW_TICKER
            elif not is_new and delta >= thresholds.min_delta and ratio >= thresholds.ratio:
                reason = AlertReason.SPIKE
            elif (
                thresholds.velocity_enabled
                and not is_new
                and current >= thresholds.velocity_min_abs
            ):
                recent = _recent_run_mentions(
                    runs, per_run, ticker, before=started_at, count=thresholds.velocity_runs
                )
                _, velocity_ratio = compute_velocity(current, recent)
                if velocity_ratio >= thresholds.velocity_ratio:
                    reason = AlertReason.VELOCITY

            if reason is None:
                continue

            blocked_until = cooldown_until.get(ticker)
            if blocked_until and started_at < blocked_until:
                result.suppressed_by_cooldown += 1
                continue

            rank = 100.0 if ratio == float("inf") else ratio
            run_hits.append((rank, ticker, reason))

        run_hits.sort(reverse=True)
        allowed = run_hits[: thresholds.max_per_run]
        result.suppressed_by_cap += len(run_hits) - len(allowed)

        for _rank, ticker, reason in allowed:
            result.total_alerts += 1
            result.per_reason[reason.value] = result.per_reason.get(reason.value, 0) + 1
            result.per_ticker[ticker] = result.per_ticker.get(ticker, 0) + 1
            cooldown_until[ticker] = started_at + timedelta(hours=thresholds.cooldown_h)

    return result


def _recent_run_mentions(
    runs: list[tuple[str, datetime]],
    per_run: dict[str, dict[str, int]],
    ticker: str,
    *,
    before: datetime,
    count: int,
) -> list[int]:
    """Nennungen des Tickers in den `count` Läufen vor `before` (fehlend = 0)."""
    previous = [rid for rid, started in runs if started < before][-count:]
    return [per_run.get(rid, {}).get(ticker, 0) for rid in reversed(previous)]
