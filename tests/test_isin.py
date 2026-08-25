"""Tests für die ISIN-Auflösung und ihren dauerhaften Cache."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from wsb_crawler.enrichment import isin as isin_module
from wsb_crawler.enrichment.isin import (
    _extract_isin,
    get_isin,
    get_isins_bulk,
    is_valid_isin,
    set_database,
)
from wsb_crawler.storage.database import Database

# Echte ISINs — die Prüfziffer muss gegen bekannte Werte stimmen, sonst ist die
# Validierung wertlos.
GME = "US36467W1099"
APPLE = "US0378331005"


def _payload(*entries: str) -> str:
    """Baut eine Antwort im Format des Suggest-Endpunkts nach."""
    return "".join(f'"{e}|Aktie|XETRA"' for e in entries)


class TestIsinValidation:
    @pytest.mark.parametrize("value", [GME, APPLE, "DE0007164600", "US5949181045", "GB0002374006"])
    def test_accepts_real_isins(self, value: str) -> None:
        assert is_valid_isin(value)

    def test_rejects_wrong_check_digit(self) -> None:
        # Letzte Stelle verfälscht — genau der Fall, den die Prüfziffer abfängt
        assert not is_valid_isin("US0378331006")

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "US123",  # zu kurz
            "US037833100A",  # Prüfstelle kein Digit
            "1S0378331005",  # Länderkürzel keine Buchstaben
            "us0378331005",  # Kleinschreibung
        ],
    )
    def test_rejects_malformed(self, value: str) -> None:
        assert not is_valid_isin(value)


class TestExtraction:
    def test_finds_the_isin_for_the_ticker(self) -> None:
        assert _extract_isin(_payload(f"GME|{GME}"), "GME") == GME

    def test_picks_the_matching_ticker_from_several(self) -> None:
        payload = _payload(f"AAPL|{APPLE}", f"GME|{GME}")
        assert _extract_isin(payload, "GME") == GME

    def test_returns_none_when_ticker_absent(self) -> None:
        assert _extract_isin(_payload(f"AAPL|{APPLE}"), "GME") is None

    def test_rejects_a_candidate_with_a_bad_check_digit(self) -> None:
        # Schützt davor, dass ein Formatwechsel der Quelle als ISIN durchgeht
        assert _extract_isin(_payload("GME|US36467W1098"), "GME") is None

    def test_ignores_garbage(self) -> None:
        assert _extract_isin("<html>nichts zu holen</html>", "GME") is None


class TestLookupAndCache:
    @pytest.fixture
    async def db(self, tmp_path: Path) -> Database:
        database = Database(tmp_path / "isin.db")
        await database.init()
        set_database(database)
        yield database
        set_database(None)  # type: ignore[arg-type]
        await database.close()

    async def test_resolves_and_persists(self, db: Database, monkeypatch: Any) -> None:
        calls: list[str] = []

        async def fake_lookup(ticker: str, company_name: str | None = None) -> str | None:
            calls.append(ticker)
            return GME

        monkeypatch.setattr(isin_module, "_lookup", fake_lookup)

        assert await get_isin("GME") == GME
        # Zweiter Aufruf kommt aus der DB — die Quelle wird nicht erneut gefragt
        assert await get_isin("GME") == GME
        assert calls == ["GME"]

    async def test_negative_result_is_remembered(self, db: Database, monkeypatch: Any) -> None:
        calls: list[str] = []

        async def fake_lookup(ticker: str, company_name: str | None = None) -> str | None:
            calls.append(ticker)
            return None

        monkeypatch.setattr(isin_module, "_lookup", fake_lookup)

        assert await get_isin("NOPE") is None
        assert await get_isin("NOPE") is None
        assert calls == ["NOPE"]  # nicht bei jedem Lauf erneut versucht

    async def test_negative_result_expires(self, db: Database, monkeypatch: Any) -> None:
        stale = (datetime.now(tz=UTC) - timedelta(days=40)).isoformat()
        await db.conn.execute(
            "INSERT INTO ticker_isin (ticker, isin, resolved_at) VALUES (?, NULL, ?)",
            ("LATER", stale),
        )
        await db.conn.commit()

        async def fake_lookup(ticker: str, company_name: str | None = None) -> str | None:
            return GME

        monkeypatch.setattr(isin_module, "_lookup", fake_lookup)
        # Ein später gelisteter Ticker darf nicht dauerhaft als "gibt es nicht" gelten
        assert await get_isin("LATER") == GME

    async def test_found_entries_never_expire(self, db: Database, monkeypatch: Any) -> None:
        stale = (datetime.now(tz=UTC) - timedelta(days=4000)).isoformat()
        await db.conn.execute(
            "INSERT INTO ticker_isin (ticker, isin, resolved_at) VALUES (?, ?, ?)",
            ("GME", GME, stale),
        )
        await db.conn.commit()

        async def boom(ticker: str, company_name: str | None = None) -> str | None:
            raise AssertionError("darf nicht erneut abgefragt werden")

        monkeypatch.setattr(isin_module, "_lookup", boom)
        assert await get_isin("GME") == GME

    async def test_company_name_is_passed_through(self, db: Database, monkeypatch: Any) -> None:
        seen: list[str | None] = []

        async def fake_lookup(ticker: str, company_name: str | None = None) -> str | None:
            seen.append(company_name)
            return GME

        monkeypatch.setattr(isin_module, "_lookup", fake_lookup)
        await get_isin("GME", "GameStop Corp.")
        assert seen == ["GameStop Corp."]

    async def test_bulk_resolves_each_ticker_once(self, db: Database, monkeypatch: Any) -> None:
        calls: list[str] = []

        async def fake_lookup(ticker: str, company_name: str | None = None) -> str | None:
            calls.append(ticker)
            return APPLE if ticker == "AAPL" else GME

        monkeypatch.setattr(isin_module, "_lookup", fake_lookup)
        result = await get_isins_bulk(["GME", "AAPL", "GME"], company_names={"GME": "GameStop"})
        assert result == {"GME": GME, "AAPL": APPLE}
        assert calls == ["GME", "AAPL"]  # Duplikat nicht doppelt abgefragt

    async def test_lookup_failure_never_raises(self, db: Database, monkeypatch: Any) -> None:
        async def boom(ticker: str, company_name: str | None = None) -> str | None:
            raise RuntimeError("Netzwerk weg")

        monkeypatch.setattr(isin_module, "_lookup", boom)
        # Die ISIN ist ein Zusatz — ein Fehler darf die Anreicherung nicht abbrechen
        assert await get_isin("GME") is None


class TestWithoutDatabase:
    async def test_returns_none_when_db_missing(self) -> None:
        set_database(None)  # type: ignore[arg-type]
        assert await get_isin("GME") is None
