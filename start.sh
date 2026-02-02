#!/bin/bash
# Quick start script for WSB-Crawler

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 WSB-Crawler Starter"
echo "======================"
echo ""

# Check if config/.env exists
if [ ! -f "config/.env" ]; then
    echo "❌ config/.env nicht gefunden!"
    echo ""
    echo "Bitte führe zuerst das Setup aus:"
    echo "   ./setup.sh"
    echo ""
    echo "Oder erstelle config/.env manuell:"
    echo "   cp config/.env.example config/.env"
    echo "   nano config/.env"
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker läuft nicht oder ist nicht verfügbar"
    echo "Bitte starte Docker und versuche es erneut."
    exit 1
fi

echo "✅ Docker läuft"
echo "✅ config/.env gefunden"
echo ""

# Show menu
echo "Wähle eine Option:"
echo ""
echo "1) Einmaliger Crawl (Vordergrund)"
echo "2) Scheduler starten (Hintergrund, stündlich)"
echo "3) Scheduler stoppen"
echo "4) Logs anzeigen"
echo "5) Status anzeigen"
echo "6) Alles stoppen und bereinigen"
echo ""
read -p "Deine Wahl [1-6]: " choice

case $choice in
    1)
        echo ""
        echo "🔄 Starte einmaligen Crawl..."
        docker-compose up
        ;;
    2)
        echo ""
        read -p "Crawl-Intervall in Minuten [60]: " interval
        interval=${interval:-60}
        interval_seconds=$((interval * 60))
        echo "🔄 Starte Scheduler (alle $interval Minuten)..."
        CRAWL_INTERVAL=$interval_seconds docker-compose --profile scheduler up -d
        echo ""
        echo "✅ Scheduler läuft im Hintergrund"
        echo "Logs anzeigen: docker-compose logs -f wsb-crawler-scheduler"
        echo "Stoppen: docker-compose --profile scheduler down"
        ;;
    3)
        echo ""
        echo "🛑 Stoppe Scheduler..."
        docker-compose --profile scheduler down
        echo "✅ Scheduler gestoppt"
        ;;
    4)
        echo ""
        echo "📋 Zeige Logs (Ctrl+C zum Beenden)..."
        echo ""
        if docker-compose ps | grep -q "wsb-crawler-scheduler"; then
            docker-compose logs -f wsb-crawler-scheduler
        elif docker-compose ps | grep -q "wsb-crawler"; then
            docker-compose logs -f wsb-crawler
        else
            echo "⚠️  Keine Container laufen"
            echo ""
            echo "Verfügbare Logs:"
            ls -lh logs/*.log 2>/dev/null || echo "Keine Log-Dateien gefunden"
        fi
        ;;
    5)
        echo ""
        echo "📊 Container Status:"
        docker-compose ps
        echo ""
        echo "💾 Daten-Verzeichnis:"
        du -sh data/* 2>/dev/null || echo "Keine Daten vorhanden"
        echo ""
        echo "📝 Log-Dateien:"
        ls -lh logs/*.log 2>/dev/null || echo "Keine Log-Dateien gefunden"
        ;;
    6)
        echo ""
        echo "🛑 Stoppe alle Container und bereinige..."
        docker-compose --profile scheduler down
        docker-compose down
        echo "✅ Alle Container gestoppt"
        echo ""
        read -p "Daten und Logs auch löschen? (y/N): " cleanup
        if [[ "$cleanup" =~ ^[Yy]$ ]]; then
            rm -rf data/output/* data/state/* logs/*
            echo "✅ Daten bereinigt"
        fi
        ;;
    *)
        echo "❌ Ungültige Auswahl"
        exit 1
        ;;
esac
