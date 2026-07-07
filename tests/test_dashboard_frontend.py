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
    assert "confirm('Lauf wirklich stoppen?')" in html
    assert "STOPPING..." in html
    assert "state.stoppingCrawl = true" in html
    assert "api('/crawl/stop', {method:'POST'})" in html
    assert 'id="stopCrawlBtn"' in html
    assert "Stoppen" in html


def test_dashboard_has_no_manual_refresh_button() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "Aktualisieren" not in html


def test_dashboard_run_button_label_is_short() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert 'id="liveCrawlBtn"' in html
    assert "status.crawl_running?'RUNNING...':'RUN'" in html
    assert "Live-Lauf" not in html


def test_alert_history_explains_columns() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "Was wird hier angezeigt?" in html
    assert "Die Alert-History zeigt alle Ticker" in html
    assert "Nennungen &amp; Faktor" in html
    assert "keine Kursdaten verfügbar" in html


def test_dashboard_run_button_shows_running_state() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "liveBtn.textContent = status.crawl_running ? 'RUNNING...' : 'RUN';" in html
    assert "RUNNING..." in html


def test_alert_history_table_headers_have_hints() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "Anzahl erkannter Ticker-Nennungen im Alert-Lauf." in html
    assert "Anstieg gegenueber der historischen Basislinie." in html
    assert "Kurs und Kursbewegung zum Alert-Zeitpunkt" in html
    assert "cursor:help" in html


def test_config_shows_cron_next_run_preview() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "configNextRunAt" in html
    assert "Nächster gespeicherter Lauf:" in html
    assert "previewCronExpression" in html
    assert "/cron/preview?count=3" in html
    assert "Nächste 3 Läufe:" in html
    assert "Promise.all([api('/config'), api('/status')])" in html


def test_alert_history_has_rich_filters() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert 'id="alertFilterReason"' in html
    assert 'id="alertFilterMentions"' in html
    assert 'id="alertFilterConfidence"' in html
    assert 'id="alertFilterDays"' in html
    assert "resetAlertFilters" in html


def test_dashboard_links_to_run_detail() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "navigate('run/${esc(r.id)}')" in html
    assert "async function renderRunDetail()" in html
    assert "api(`/runs/${encodeURIComponent(state.runId)}`)" in html
    assert "Top-Ticker in diesem Lauf" in html
