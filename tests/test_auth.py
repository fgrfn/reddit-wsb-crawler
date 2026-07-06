"""Tests für die optionale Dashboard-Authentifizierung."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from wsb_crawler.api.auth import AUTH_TOKEN_ENV, request_is_authorized


def _basic(user: str, password: str) -> dict[str, str]:
    raw = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


# ── Reine Logik (request_is_authorized) ──────────────────────────────────────


def test_no_token_means_auth_disabled() -> None:
    assert request_is_authorized(client_host="10.0.0.5", auth_header=None, method="GET", token="")


def test_loopback_bypasses_auth() -> None:
    assert request_is_authorized(
        client_host="127.0.0.1", auth_header=None, method="GET", token="secret"
    )
    assert request_is_authorized(client_host="::1", auth_header=None, method="GET", token="secret")


def test_remote_without_credentials_is_rejected() -> None:
    assert not request_is_authorized(
        client_host="10.0.0.5", auth_header=None, method="GET", token="secret"
    )


def test_remote_with_correct_token_is_allowed() -> None:
    header = _basic("admin", "secret")["Authorization"]
    assert request_is_authorized(
        client_host="10.0.0.5", auth_header=header, method="GET", token="secret"
    )


def test_remote_with_wrong_token_is_rejected() -> None:
    header = _basic("admin", "nope")["Authorization"]
    assert not request_is_authorized(
        client_host="10.0.0.5", auth_header=header, method="GET", token="secret"
    )


def test_options_preflight_always_allowed() -> None:
    assert request_is_authorized(
        client_host="10.0.0.5", auth_header=None, method="OPTIONS", token="secret"
    )


def test_malformed_header_is_rejected() -> None:
    assert not request_is_authorized(
        client_host="10.0.0.5", auth_header="Basic not-base64!!", method="GET", token="secret"
    )
    assert not request_is_authorized(
        client_host="10.0.0.5", auth_header="Bearer secret", method="GET", token="secret"
    )


# ── Middleware im echten App-Kontext (TestClient host = "testclient" ≠ loopback) ──


def test_app_requires_auth_when_token_set(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from wsb_crawler.api.server import app

    monkeypatch.setenv(AUTH_TOKEN_ENV, "secret")
    client = TestClient(app)

    assert client.get("/api/about").status_code == 401
    assert client.get("/api/about", headers=_basic("x", "secret")).status_code == 200


def test_app_open_when_token_absent(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from wsb_crawler.api.server import app

    monkeypatch.delenv(AUTH_TOKEN_ENV, raising=False)
    client = TestClient(app)

    assert client.get("/api/about").status_code == 200
