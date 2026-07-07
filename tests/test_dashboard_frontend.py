from __future__ import annotations

from pathlib import Path

INDEX = Path("src/wsb_crawler/api/static/index.html")


def test_dashboard_frontend_loads_panels_fail_soft() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "const API_TIMEOUT_MS = 8000" in html
    assert "function apiFallback" in html
    assert "apiFallback(`/tickers?days=${state.days}`, [])" in html
    assert "apiFallback('/alerts?limit=5', [])" in html
    assert "apiFallback('/runs?limit=4', [])" in html
    assert "apiFallback(`/mentions/daily?days=${state.days}`, {days:state.days,data:[]})" in html
    assert "Dashboard wird geladen" in html
