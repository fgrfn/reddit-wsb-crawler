"""Tests für das Velocity-Signal (Frühwarnung über Lauf-Beschleunigung)."""

from __future__ import annotations

from pathlib import Path

import pytest

from wsb_crawler.analysis.detector import (
    _candidate_rank,
    _confidence_score,
    compute_velocity,
    velocity_triggers,
)
from wsb_crawler.models import AlertReason, SpikeResult
from wsb_crawler.storage.database import Database


class TestComputeVelocity:
    def test_empty_window_has_no_basis(self) -> None:
        assert compute_velocity(20, []) == (0.0, 0.0)

    def test_zero_average_has_no_basis(self) -> None:
        # Ticker war in den letzten Läufen gar nicht da → NEW_TICKER-Fall
        assert compute_velocity(20, [0, 0, 0]) == (0.0, 0.0)

    def test_average_and_ratio(self) -> None:
        avg, ratio = compute_velocity(30, [10, 10, 10])
        assert avg == 10.0
        assert ratio == 3.0

    def test_missing_runs_count_as_zero(self) -> None:
        # 5, 0, 0 → Ø 1.67; 10 Nennungen sind also 6x
        avg, ratio = compute_velocity(10, [5, 0, 0])
        assert avg == pytest.approx(1.667, abs=0.01)
        assert ratio == pytest.approx(6.0, abs=0.05)

    def test_decline_gives_ratio_below_one(self) -> None:
        _, ratio = compute_velocity(5, [20, 20])
        assert ratio == 0.25


class TestVelocityTriggers:
    def test_fires_on_acceleration(self) -> None:
        assert velocity_triggers(30, [10, 10, 10], min_abs=8, ratio_threshold=2.5)

    def test_noise_floor_blocks_small_numbers(self) -> None:
        # 6 gegen Ø 2 ist 3x, aber unter dem Rauschfilter
        assert not velocity_triggers(6, [2, 2, 2], min_abs=8, ratio_threshold=2.5)

    def test_below_threshold_does_not_fire(self) -> None:
        assert not velocity_triggers(20, [10, 10, 10], min_abs=8, ratio_threshold=2.5)

    def test_no_history_does_not_fire(self) -> None:
        assert not velocity_triggers(50, [], min_abs=8, ratio_threshold=2.5)

    def test_all_zero_history_does_not_fire(self) -> None:
        assert not velocity_triggers(50, [0, 0], min_abs=8, ratio_threshold=2.5)

    def test_threshold_is_inclusive(self) -> None:
        assert velocity_triggers(25, [10, 10], min_abs=8, ratio_threshold=2.5)


def _spike(**kw: object) -> SpikeResult:
    base = dict(
        ticker="GME",
        current_mentions=20,
        avg_mentions=10.0,
        ratio=2.0,
        delta=10,
        is_new=False,
        reason=AlertReason.VELOCITY,
    )
    base.update(kw)
    return SpikeResult(**base)  # type: ignore[arg-type]


class TestScoring:
    def test_velocity_raises_confidence(self) -> None:
        without = _confidence_score(_spike())
        with_vel = _confidence_score(_spike(velocity_ratio=4.0, velocity_avg=5.0))
        assert with_vel > without

    def test_velocity_contribution_is_capped(self) -> None:
        moderate = _confidence_score(_spike(velocity_ratio=4.0))
        extreme = _confidence_score(_spike(velocity_ratio=99.0))
        assert extreme - moderate <= 12

    def test_velocity_raises_candidate_rank(self) -> None:
        without = _candidate_rank(_spike())
        with_vel = _candidate_rank(_spike(velocity_ratio=5.0))
        assert with_vel > without


class TestRecentRunMentions:
    @pytest.fixture
    async def db(self, tmp_path: Path) -> Database:
        database = Database(tmp_path / "v.db")
        await database.init()
        yield database
        await database.close()

    async def test_returns_newest_first(self, db: Database) -> None:
        for count in (5, 10, 15):
            rid = await db.start_run(["wsb"])
            await db.save_run_mentions(rid, {"GME": count})
            await db.finish_run(rid, 10, 10)
        assert await db.get_recent_run_mentions("GME", runs=3) == [15, 10, 5]

    async def test_missing_mentions_are_zero(self, db: Database) -> None:
        rid1 = await db.start_run(["wsb"])
        await db.save_run_mentions(rid1, {"AMC": 7})  # GME fehlt
        await db.finish_run(rid1, 10, 10)
        rid2 = await db.start_run(["wsb"])
        await db.save_run_mentions(rid2, {"GME": 12})
        await db.finish_run(rid2, 10, 10)
        assert await db.get_recent_run_mentions("GME", runs=2) == [12, 0]

    async def test_excludes_current_run(self, db: Database) -> None:
        rid1 = await db.start_run(["wsb"])
        await db.save_run_mentions(rid1, {"GME": 5})
        await db.finish_run(rid1, 10, 10)
        current = await db.start_run(["wsb"])
        await db.save_run_mentions(current, {"GME": 40})
        await db.finish_run(current, 10, 10)
        assert await db.get_recent_run_mentions("GME", runs=5, exclude_run_id=current) == [5]

    async def test_respects_window_size(self, db: Database) -> None:
        for count in (1, 2, 3, 4, 5):
            rid = await db.start_run(["wsb"])
            await db.save_run_mentions(rid, {"GME": count})
            await db.finish_run(rid, 10, 10)
        assert await db.get_recent_run_mentions("GME", runs=2) == [5, 4]

    async def test_ignores_unfinished_runs(self, db: Database) -> None:
        rid = await db.start_run(["wsb"])
        await db.save_run_mentions(rid, {"GME": 9})
        await db.finish_run(rid, 10, 10)
        # Laufender Crawl (kein finished_at) darf das Fenster nicht verfälschen
        running = await db.start_run(["wsb"])
        await db.save_run_mentions(running, {"GME": 99})
        assert await db.get_recent_run_mentions("GME", runs=3) == [9]

    async def test_empty_database(self, db: Database) -> None:
        assert await db.get_recent_run_mentions("GME", runs=3) == []


class TestDetectorIntegration:
    """Velocity muss greifen, wo der 30-Tage-Check noch schweigt."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> Database:
        database = Database(tmp_path / "int.db")
        await database.init()
        for key, value in (
            ("reddit_client_id", "x"),
            ("reddit_client_secret", "y"),
            ("discord_webhook_url", "https://discord.com/api/webhooks/1/z"),
        ):
            await database.set_setting(key, value)
        yield database
        await database.close()

    @staticmethod
    async def _seed_and_analyze(db: Database, current: int) -> list:
        from unittest.mock import AsyncMock, patch

        from wsb_crawler.analysis import detector

        # Ticker dümpelt zuletzt bei 4-6 Nennungen pro Lauf
        for count in (6, 5, 4, 5, 6):
            rid = await db.start_run(["wsb"])
            await db.save_run_mentions(rid, {"HTZ": count})
            await db.finish_run(rid, 10, 10)

        run_id = await db.start_run(["wsb"])
        counts = {"HTZ": current}
        await db.save_run_mentions(run_id, counts)

        with (
            patch.object(detector, "get_prices_bulk", new=AsyncMock(return_value={"HTZ": None})),
            patch.object(detector, "get_news_bulk", new=AsyncMock(return_value={"HTZ": []})),
            patch.object(detector, "resolve_names_bulk", new=AsyncMock(return_value={"HTZ": None})),
        ):
            return await detector.analyze_mentions(counts, db, run_id=run_id)

    async def test_velocity_alert_fires_when_classic_spike_is_silent(self, db: Database) -> None:
        alerts = await self._seed_and_analyze(db, current=18)
        assert [a.reason for a in alerts] == [AlertReason.VELOCITY]
        spike = alerts[0].spike
        # Der klassische Check hätte nicht ausgelöst (ratio < 2.0)
        assert spike.ratio < 2.0
        assert spike.velocity_ratio == pytest.approx(3.6, abs=0.05)
        assert spike.confidence > 0

    async def test_disabled_produces_no_alert(self, db: Database) -> None:
        await db.set_setting("alert_velocity_enabled", "false")
        assert await self._seed_and_analyze(db, current=18) == []

    async def test_steady_mentions_do_not_fire(self, db: Database) -> None:
        # 6 Nennungen bei Ø 5 → nur 1.2x, keine Beschleunigung
        assert await self._seed_and_analyze(db, current=6) == []
