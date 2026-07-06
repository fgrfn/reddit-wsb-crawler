"""
Tests für die Konfigurationsauflösung (config.py) — hier speziell der DB-Pfad.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wsb_crawler.config import _resolve_db_path


class TestResolveDbPath:
    def test_default_is_cwd_relative(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("WSB_DB_PATH", raising=False)
        assert _resolve_db_path() == Path("data/wsb_crawler.db")

    def test_env_override_wins(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("WSB_DB_PATH", "/var/lib/wsb/wsb.db")
        assert _resolve_db_path() == Path("/var/lib/wsb/wsb.db")

    def test_env_override_expands_user(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("WSB_DB_PATH", "~/wsb/data.db")
        resolved = _resolve_db_path()
        assert "~" not in str(resolved)
        assert str(resolved).endswith("wsb/data.db")

    def test_blank_env_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("WSB_DB_PATH", "   ")
        assert _resolve_db_path() == Path("data/wsb_crawler.db")
