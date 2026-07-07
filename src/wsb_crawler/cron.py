"""
Abhängigkeitsfreie 5-Feld-Cron-Auswertung für den Crawl-Scheduler.

Unterstützt Standard-Cron-Syntax `Minute Stunde Tag-des-Monats Monat Wochentag`
mit `*`, Listen (`1,15,30`), Bereichen (`9-17`), Schritten (`*/2`, `0-30/5`).
Wochentag: 0 = Sonntag … 6 = Samstag (7 wird ebenfalls als Sonntag akzeptiert).

Bewusst simpel und ohne externe Library (z. B. croniter), um das Projekt schlank
zu halten. Kein Sekunden-Feld — der Scheduler arbeitet minutengenau.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# (low, high) je Feld: Minute, Stunde, Tag, Monat, Wochentag
_FIELD_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    """Parst ein einzelnes Cron-Feld zu einer Menge erlaubter Werte."""
    values: set[int] = set()
    for part in field.split(","):
        if not part:
            raise ValueError(f"Leeres Cron-Segment in '{field}'")
        step = 1
        rng = part
        if "/" in part:
            rng, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Ungültige Schrittweite in '{part}'")
        if rng == "*":
            start, end = lo, hi
        elif "-" in rng:
            a, b = rng.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(rng)
        if start < lo or end > hi or start > end:
            raise ValueError(f"Cron-Wert '{part}' außerhalb {lo}-{hi}")
        values.update(range(start, end + 1, step))
    return values


class CronSchedule:
    """Vorgeparste Cron-Regel mit `next_after()`-Berechnung."""

    def __init__(self, expression: str) -> None:
        fields = expression.split()
        if len(fields) != 5:
            raise ValueError(
                f"Cron-Ausdruck braucht genau 5 Felder, hat {len(fields)}: '{expression}'"
            )
        self.expression = expression
        self.minute = _parse_field(fields[0], *_FIELD_BOUNDS[0])
        self.hour = _parse_field(fields[1], *_FIELD_BOUNDS[1])
        self.dom = _parse_field(fields[2], *_FIELD_BOUNDS[2])
        self.month = _parse_field(fields[3], *_FIELD_BOUNDS[3])
        # Wochentag: 7 → 0 (beide = Sonntag)
        self.dow = {0 if v == 7 else v for v in _parse_field(fields[4], *_FIELD_BOUNDS[4])}
        # Für die OR-Semantik von Tag-des-Monats/Wochentag (Standard-Cron):
        # sind beide eingeschränkt, matcht ein Tag wenn EINES zutrifft.
        self._dom_restricted = fields[2] != "*"
        self._dow_restricted = fields[4] != "*"

    def _matches(self, moment: datetime) -> bool:
        if moment.minute not in self.minute:
            return False
        if moment.hour not in self.hour:
            return False
        if moment.month not in self.month:
            return False
        # cron-Wochentag: So=0..Sa=6  (Python weekday(): Mo=0..So=6)
        cron_dow = (moment.weekday() + 1) % 7
        dom_ok = moment.day in self.dom
        dow_ok = cron_dow in self.dow
        if self._dom_restricted and self._dow_restricted:
            return dom_ok or dow_ok
        if self._dom_restricted:
            return dom_ok
        if self._dow_restricted:
            return dow_ok
        return True

    def next_after(self, after: datetime) -> datetime:
        """Nächster passender Zeitpunkt *strikt nach* `after` (minutengenau)."""
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # Ein Jahr an Minuten ist die Obergrenze — jede gültige Regel matcht früher.
        for _ in range(366 * 24 * 60):
            if self._matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError(f"Cron-Ausdruck '{self.expression}' matcht innerhalb eines Jahres nicht")


def validate_cron(expression: str) -> None:
    """Wirft ValueError, wenn der Ausdruck ungültig ist (für Config-Validierung)."""
    CronSchedule(expression)


def next_run(expression: str, after: datetime) -> datetime:
    """Bequemer Einzelaufruf: nächster Lauf nach `after`."""
    return CronSchedule(expression).next_after(after)
