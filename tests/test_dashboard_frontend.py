from __future__ import annotations

from pathlib import Path

INDEX = Path("src/wsb_crawler/api/static/index.html")


def test_dashboard_root_uses_flex_shell() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert "#app { display:flex; min-height:100vh; }" in html
    assert ".app { display:flex; min-height:100vh; }" not in html
