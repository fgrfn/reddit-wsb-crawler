"""Tests für die abhängigkeitsfreie Cron-Auswertung (cron.py)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from wsb_crawler.cron import CronSchedule, next_run, validate_cron


def _dt(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


class TestNextRun:
    def test_every_two_hours_on_the_hour(self) -> None:
        # 0 */2 * * *  → 00,02,04,… :00
        got = next_run("0 */2 * * *", _dt(2026, 7, 6, 14, 24))
        assert got == _dt(2026, 7, 6, 16, 0)

    def test_every_minute(self) -> None:
        got = next_run("* * * * *", _dt(2026, 7, 6, 14, 24))
        assert got == _dt(2026, 7, 6, 14, 25)

    def test_specific_time_next_day(self) -> None:
        # 30 9 * * *  → täglich 09:30; von 10:00 → morgen 09:30
        got = next_run("30 9 * * *", _dt(2026, 7, 6, 10, 0))
        assert got == _dt(2026, 7, 7, 9, 30)

    def test_list_and_range(self) -> None:
        got = next_run("0,30 9-17 * * *", _dt(2026, 7, 6, 17, 5))
        assert got == _dt(2026, 7, 6, 17, 30)

    def test_strictly_after(self) -> None:
        # Exakt auf einem Treffer → nächster Treffer, nicht derselbe
        got = next_run("0 * * * *", _dt(2026, 7, 6, 15, 0))
        assert got == _dt(2026, 7, 6, 16, 0)

    def test_weekday_monday(self) -> None:
        # 0 0 * * 1 → Montag 00:00. 2026-07-06 ist ein Montag.
        got = next_run("0 0 * * 1", _dt(2026, 7, 6, 1, 0))
        assert got == _dt(2026, 7, 13, 0, 0)  # nächster Montag

    def test_sunday_as_0_and_7(self) -> None:
        after = _dt(2026, 7, 6, 12, 0)  # Montag
        assert next_run("0 0 * * 0", after) == next_run("0 0 * * 7", after)

    def test_dom_and_dow_or_semantics(self) -> None:
        # Beide eingeschränkt → OR: Tag 15 ODER Freitag(5)
        # 2026-07-06 (Mo) → nächster Treffer ist Fr 2026-07-10
        got = next_run("0 0 15 * 5", _dt(2026, 7, 6, 12, 0))
        assert got == _dt(2026, 7, 10, 0, 0)


class TestValidation:
    def test_valid_expression_ok(self) -> None:
        validate_cron("*/15 9-17 * * 1-5")  # kein Fehler

    @pytest.mark.parametrize(
        "expr",
        [
            "* * * *",  # zu wenige Felder
            "60 * * * *",  # Minute außerhalb 0-59
            "* 24 * * *",  # Stunde außerhalb
            "* * 0 * *",  # Tag < 1
            "* * * 13 *",  # Monat > 12
            "*/0 * * * *",  # Schritt 0
            "5-2 * * * *",  # start > end
        ],
    )
    def test_invalid_expressions_raise(self, expr: str) -> None:
        with pytest.raises(ValueError):
            validate_cron(expr)


def test_schedule_reuses_parse() -> None:
    sched = CronSchedule("0 12 * * *")
    a = sched.next_after(_dt(2026, 7, 6, 13, 0))
    assert a == _dt(2026, 7, 7, 12, 0)
