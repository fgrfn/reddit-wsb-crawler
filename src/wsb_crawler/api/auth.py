"""
Optionale HTTP-Basic-Authentifizierung fürs Dashboard.

Standardmäßig **deaktiviert** — das Verhalten ist identisch mit früher, solange
``WSB_AUTH_TOKEN`` nicht gesetzt ist. Wird die Variable gesetzt, verlangt der
Server für alle nicht-lokalen Zugriffe HTTP-Basic-Auth mit dem Token als
Passwort (Benutzername beliebig).

Loopback-Clients (127.0.0.1/::1) werden bewusst durchgelassen: so funktioniert
der Docker-HEALTHCHECK weiter und lokale Zugriffe brauchen kein Token —
konsistent mit der bisherigen "localhost = vertrauenswürdig"-Philosophie.
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
from ipaddress import ip_address

AUTH_TOKEN_ENV = "WSB_AUTH_TOKEN"
REALM = "WSB-Crawler"


def get_auth_token() -> str:
    """Liest das Token frisch aus der Umgebung (kein Cache → Tests/Reload-freundlich)."""
    return os.getenv(AUTH_TOKEN_ENV, "").strip()


def _client_is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ip_address(host).is_loopback
    except ValueError:
        # "testclient", Hostnamen etc. sind nicht loopback
        return False


def _basic_auth_ok(auth_header: str | None, token: str) -> bool:
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    # Format "user:pass" — verglichen wird das Passwort (Benutzername egal).
    _, sep, password = decoded.partition(":")
    if not sep:
        return False
    return secrets.compare_digest(password, token)


def request_is_authorized(
    *,
    client_host: str | None,
    auth_header: str | None,
    method: str,
    token: str,
) -> bool:
    """Zentrale, seiteneffektfreie Autorisierungs-Entscheidung (unit-testbar)."""
    if not token:
        return True  # Auth deaktiviert
    if method == "OPTIONS":
        return True  # CORS-Preflight nie blocken
    if _client_is_loopback(client_host):
        return True  # lokaler Zugriff / Docker-Healthcheck
    return _basic_auth_ok(auth_header, token)
