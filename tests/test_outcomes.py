"""Tests für Alert-Erfolgskontrolle und Schwellwert-Simulator."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wsb_crawler.analysis import outcomes
from wsb_crawler.analysis.simulate import SimulationThresholds, simulate_thresholds
from wsb_crawler.models import (
    Alert,
    AlertReason,
    MarketStatus,
    PriceData,
    SpikeResult,
)
from wsb_crawler.storage.database import Database


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "o.db")
    await database.init()
    yield database
    await database.close()


def _alert(ticker: str, price: float, hours_ago: float) -> Alert:
    spike = SpikeResult(
        ticker=ticker,
        current_mentions=25,
        avg_mentions=6.0,
        ratio=4.0,
        delta=19,
        is_new=False,
        reason=AlertReason.SPIKE,
        price_data=PriceData(
            ticker=ticker,
            company_name=None,
            price=price,
            market_status=MarketStatus.OPEN,
        ),
    )
    alert = Alert(ticker=ticker, reason=AlertReason.SPIKE, spike=spike)
    alert.triggered_at = dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours_ago)
    return alert


class TestAwaitingOutcome:
    async def test_only_alerts_past_the_window_are_due(self, db: Database) -> None:
        await db.save_alert(_alert("OLD", 10.0, hours_ago=2))
        await db.save_alert(_alert("NEW", 10.0, hours_ago=0))
        due = await db.get_alerts_awaiting_outcome(1)
        assert [row["ticker"] for row in due] == ["OLD"]

    async def test_24h_window_needs_a_full_day(self, db: Database) -> None:
        await db.save_alert(_alert("GME", 10.0, hours_ago=2))
        assert await db.get_alerts_awaiting_outcome(24) == []
        await db.save_alert(_alert("AMC", 5.0, hours_ago=30))
        assert [row["ticker"] for row in await db.get_alerts_awaiting_outcome(24)] == ["AMC"]

    async def test_measured_alerts_are_not_due_again(self, db: Database) -> None:
        await db.save_alert(_alert("GME", 10.0, hours_ago=2))
        due = await db.get_alerts_awaiting_outcome(1)
        await db.save_alert_outcome(due[0]["id"], 1, 11.0)
        assert await db.get_alerts_awaiting_outcome(1) == []

    async def test_stale_alerts_are_abandoned(self, db: Database) -> None:
        # Älter als max_age_days → wird nicht endlos weiter versucht
        await db.save_alert(_alert("OLD", 10.0, hours_ago=24 * 30))
        assert await db.get_alerts_awaiting_outcome(1, max_age_days=7) == []

    async def test_alerts_without_price_are_skipped(self, db: Database) -> None:
        spike = SpikeResult(
            ticker="XYZ",
            current_mentions=25,
            avg_mentions=6.0,
            ratio=4.0,
            delta=19,
            is_new=False,
            reason=AlertReason.SPIKE,
        )
        alert = Alert(ticker="XYZ", reason=AlertReason.SPIKE, spike=spike)
        alert.triggered_at = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
        await db.save_alert(alert)
        assert await db.get_alerts_awaiting_outcome(1) == []

    async def test_unknown_window_is_rejected(self, db: Database) -> None:
        with pytest.raises(ValueError):
            await db.get_alerts_awaiting_outcome(3)
        with pytest.raises(ValueError):
            await db.save_alert_outcome(1, 3, 10.0)


class TestOutcomeStats:
    async def test_hit_rate_and_average(self, db: Database) -> None:
        await db.save_alert(_alert("UP", 10.0, hours_ago=2))
        await db.save_alert(_alert("DOWN", 10.0, hours_ago=2))
        due = {row["ticker"]: row["id"] for row in await db.get_alerts_awaiting_outcome(1)}
        await db.save_alert_outcome(due["UP"], 1, 11.5)  # +15 %
        await db.save_alert_outcome(due["DOWN"], 1, 9.8)  # -2 %

        stats = await db.get_alert_outcome_stats(days=30, hit_threshold_pct=3.0)
        row = next(s for s in stats if s["reason"] == "spike")
        assert row["alerts"] == 2
        assert row["measured_1h"] == 2
        assert row["avg_1h"] == pytest.approx(6.5, abs=0.01)  # (15 + -2) / 2
        assert row["hit_rate_1h"] == 50.0  # 1 von 2 über +3 %

    async def test_unmeasured_alerts_do_not_dilute_the_rate(self, db: Database) -> None:
        await db.save_alert(_alert("UP", 10.0, hours_ago=2))
        await db.save_alert(_alert("PENDING", 10.0, hours_ago=0))
        due = await db.get_alerts_awaiting_outcome(1)
        await db.save_alert_outcome(due[0]["id"], 1, 12.0)  # +20 %

        row = next(s for s in await db.get_alert_outcome_stats(days=30) if s["reason"] == "spike")
        assert row["alerts"] == 2
        assert row["measured_1h"] == 1
        assert row["hit_rate_1h"] == 100.0  # nur der gemessene zählt

    async def test_no_measurements_yields_none(self, db: Database) -> None:
        await db.save_alert(_alert("GME", 10.0, hours_ago=0))
        row = next(s for s in await db.get_alert_outcome_stats(days=30) if s["reason"] == "spike")
        assert row["hit_rate_1h"] is None
        assert row["avg_1h"] is None


class TestUpdateAlertOutcomes:
    async def test_writes_measured_prices(self, db: Database) -> None:
        await db.save_alert(_alert("GME", 10.0, hours_ago=2))
        prices = {"GME": PriceData(ticker="GME", company_name=None, price=12.0)}
        with patch.object(outcomes, "get_prices_bulk", new=AsyncMock(return_value=prices)):
            updated = await outcomes.update_alert_outcomes(db)
        assert updated == {1: 1}
        row = next(s for s in await db.get_alert_outcome_stats(days=30) if s["reason"] == "spike")
        assert row["avg_1h"] == pytest.approx(20.0, abs=0.01)

    async def test_missing_price_leaves_alert_due(self, db: Database) -> None:
        await db.save_alert(_alert("GME", 10.0, hours_ago=2))
        with patch.object(outcomes, "get_prices_bulk", new=AsyncMock(return_value={"GME": None})):
            assert await outcomes.update_alert_outcomes(db) == {}
        assert len(await db.get_alerts_awaiting_outcome(1)) == 1  # nächster Lauf versucht erneut

    async def test_price_error_does_not_raise(self, db: Database) -> None:
        await db.save_alert(_alert("GME", 10.0, hours_ago=2))
        with patch.object(
            outcomes, "get_prices_bulk", new=AsyncMock(side_effect=RuntimeError("429"))
        ):
            assert await outcomes.update_alert_outcomes(db) == {}


class TestSimulator:
    @staticmethod
    async def _seed(db: Database, counts: list[int], ticker: str = "GME") -> None:
        for count in counts:
            rid = await db.start_run(["wsb"])
            await db.save_run_mentions(rid, {ticker: count})
            await db.finish_run(rid, 10, 10)

    async def test_velocity_toggle_changes_result(self, db: Database) -> None:
        await self._seed(db, [5, 6, 5, 7, 6, 20, 25])
        base = dict(min_abs=20, min_delta=10, ratio=2.0, velocity_ratio=2.5, velocity_min_abs=8)
        with_vel = await simulate_thresholds(
            db, SimulationThresholds(**base, velocity_enabled=True), days=30
        )
        without = await simulate_thresholds(
            db, SimulationThresholds(**base, velocity_enabled=False), days=30
        )
        assert with_vel.total_alerts > without.total_alerts
        assert with_vel.per_reason.get("velocity", 0) >= 1

    async def test_empty_database_returns_zero(self, db: Database) -> None:
        result = await simulate_thresholds(db, SimulationThresholds(), days=30)
        assert result.total_alerts == 0
        assert result.runs_evaluated == 0

    async def test_reports_runs_and_per_day(self, db: Database) -> None:
        await self._seed(db, [5, 6, 30])
        result = await simulate_thresholds(db, SimulationThresholds(), days=10)
        assert result.runs_evaluated == 3
        payload = result.as_dict()
        assert payload["days"] == 10
        assert payload["alerts_per_day"] == round(payload["total_alerts"] / 10, 2)

    async def test_cap_per_run_limits_alerts(self, db: Database) -> None:
        # Viele gleichzeitig auffällige Ticker → max_per_run greift
        rid = await db.start_run(["wsb"])
        await db.save_run_mentions(rid, {f"T{i}": 50 for i in range(8)})
        await db.finish_run(rid, 10, 10)
        result = await simulate_thresholds(
            db, SimulationThresholds(max_per_run=3, velocity_enabled=False), days=10
        )
        assert result.total_alerts <= 3
        assert result.suppressed_by_cap >= 1

    async def test_min_relevant_accounts_for_velocity_floor(self) -> None:
        t = SimulationThresholds(
            min_abs=20, min_delta=10, velocity_enabled=True, velocity_min_abs=8
        )
        assert t.min_relevant == 8
        t_off = SimulationThresholds(min_abs=20, min_delta=10, velocity_enabled=False)
        assert t_off.min_relevant == 10
