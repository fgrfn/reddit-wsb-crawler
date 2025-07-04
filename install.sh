#!/bin/bash
# Installationsskript für reddit-wbs-crawler

echo "Erstelle virtuelle Umgebung ..."
python3 -m venv .venv

echo "Aktiviere virtuelle Umgebung ..."
source .venv/bin/activate

echo "Installiere Python-Abhängigkeiten ..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Erstelle benötigte Ordner ..."
mkdir -p data/input data/output logs logs/archive config

echo "Erstelle leere .env Datei (falls nicht vorhanden) ..."
if [ ! -f config/.env ]; then
    echo "# Beispiel-Umgebungsvariablen" > config/.env
    echo "OPENAI_API_KEY=" >> config/.env
    echo "REDDIT_CLIENT_ID=" >> config/.env
    echo "REDDIT_CLIENT_SECRET=" >> config/.env
    echo "REDDIT_USER_AGENT=" >> config/.env
    echo "SUBREDDITS=wallstreetbets" >> config/.env
fi

echo "Installation abgeschlossen!"