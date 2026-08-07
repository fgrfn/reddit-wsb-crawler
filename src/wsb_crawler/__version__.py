"""Paketversion — Single Source of Truth ist der Git-Tag (via hatch-vcs).

Die Version wird beim Build/Install aus dem Git-Tag in die Paket-Metadaten
geschrieben und hier ausgelesen. Kein Hardcode mehr → keine Versions-Drift.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wsb-crawler")
except PackageNotFoundError:  # Paket nicht installiert (z.B. direkter Source-Run)
    __version__ = "0.0.0+unknown"
