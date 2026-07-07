from __future__ import annotations

from pathlib import Path

INDEX = Path("src/wsb_crawler/api/static/index.html")


def test_dashboard_root_uses_flex_shell() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "#app { display:flex; min-height:100vh; }" in html
    assert ".app { display:flex; min-height:100vh; }" not in html


def test_dashboard_uses_status_websocket_instead_of_refresh_timer() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "/api/ws/status" in html
    assert "dashboardWs" in html
    assert "function updateDashboardLive" in html
    assert "function scheduleRefresh" not in html
    assert "refreshTimer" not in html


def test_config_fields_render_help_texts() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "Client-ID deiner Reddit Script-App." in html
    assert "Discord Servereinstellungen" in html
    assert "Komma-separiert, z.B. wallstreetbets, wallstreetbetsGER." in html
    assert "Mindestanzahl, ab der ein neuer Ticker als Kandidat gilt." in html
    assert "${f.h?`<span class=\"hint\">${esc(f.h)}</span>`:''}" in html


def test_dashboard_exposes_stop_crawl_action() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "async function stopCrawl()" in html
    assert "api('/crawl/stop', {method:'POST'})" in html
    assert 'id="stopCrawlBtn"' in html
    assert "Stoppen" in html


def test_dashboard_has_no_manual_refresh_button() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "Aktualisieren" not in html


def test_dashboard_run_button_label_is_short() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert 'id="liveCrawlBtn"' in html
    assert ">RUN</button>" in html
    assert "Live-Lauf" not in html
