#!/usr/bin/env bash
# update.sh — WSB-Crawler auf dem Server aktualisieren
# Verwendung: bash update.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "→ Neueste Änderungen holen..."
git pull

echo "→ Python-Abhängigkeiten aktualisieren..."
if [ -f venv/bin/python ]; then
    venv/bin/python -m pip install -q -e . --upgrade
else
    echo "  ⚠ Kein venv gefunden — bitte zuerst: python3 setup.py"
    exit 1
fi

echo "→ Service neu starten..."
if [ "$(id -u)" -eq 0 ]; then
    systemctl restart wsb-crawler
else
    systemctl --user restart wsb-crawler
fi

echo "✓ Update abgeschlossen."
