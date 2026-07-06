"""Regression tests for the FastAPI dashboard server."""

from __future__ import annotations


def test_fastapi_app_imports() -> None:
    from wsb_crawler.api.server import app

    assert app.title == "WSB-Crawler Dashboard"
