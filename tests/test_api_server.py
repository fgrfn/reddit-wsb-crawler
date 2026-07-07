"""Regression tests for the FastAPI dashboard server."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_fastapi_app_imports() -> None:
    from wsb_crawler.api.server import app

    assert app.title == "WSB-Crawler Dashboard"


def test_about_endpoint_exposes_version() -> None:
    from wsb_crawler.__version__ import __version__
    from wsb_crawler.api.server import app

    client = TestClient(app)
    response = client.get("/api/about")

    assert response.status_code == 200
    assert response.json()["version"] == __version__


def test_status_websocket_route_is_registered() -> None:
    from wsb_crawler.api.server import app

    assert any(getattr(route, "path", None) == "/api/ws/status" for route in app.routes)


def test_stop_crawl_route_is_registered() -> None:
    from wsb_crawler.api.server import app

    assert any(getattr(route, "path", None) == "/api/crawl/stop" for route in app.routes)
