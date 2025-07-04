#!/bin/bash

echo "🌐 Starte Reddit Crawler Webinterface ..."

## Virtuelle Umgebung aktivieren
#if [ -d "venv" ]; then
#    source ./venv/bin/activate
#else
#    echo "❌ Virtuelle Umgebung nicht gefunden. Bitte zuerst setup.sh ausführen."
#    exit 1
#fi

# Projektverzeichnis ermitteln (optional)
#PROJECT_DIR=$(dirname "$(realpath "$0")")
#cd "$PROJECT_DIR"

# Starte Streamlit App
streamlit run src/web_app.py
