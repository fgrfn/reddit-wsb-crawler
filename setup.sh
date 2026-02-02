#!/bin/bash
# Quick setup script for WSB-Crawler

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 WSB-Crawler Setup"
echo "===================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker ist nicht installiert. Bitte installiere Docker erst:"
    echo "   https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker läuft nicht. Bitte starte Docker und versuche es erneut."
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose ist nicht installiert. Bitte installiere Docker Compose erst:"
    echo "   https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker gefunden und läuft"
echo ""

# Check if config/.env exists
if [ ! -f "config/.env" ]; then
    echo "⚙️  Erstelle config/.env aus Vorlage..."
    if [ -f "config/.env.example" ]; then
        cp config/.env.example config/.env
        echo "✅ config/.env erstellt"
        echo ""
        echo "⚠️  WICHTIG: Bearbeite config/.env und füge deine API-Keys ein:"
        echo "   - REDDIT_CLIENT_ID"
        echo "   - REDDIT_CLIENT_SECRET"
        echo "   - NEWSAPI_KEY"
        echo "   - DISCORD_WEBHOOK_URL"
        echo ""
        echo "Fortfahren mit Setup? (y/n)"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo "Setup abgebrochen. Bearbeite config/.env und führe das Script erneut aus."
            exit 0
        fi
    else
        echo "❌ config/.env.example nicht gefunden!"
        exit 1
    fi
else
    echo "✅ config/.env gefunden"
fi

echo ""
echo "🏗️  Baue Docker-Image..."
docker-compose build

echo ""
echo "✅ Setup abgeschlossen!"
echo ""
echo "Nächste Schritte:"
echo "=================="
echo ""
echo "📝 1. Bearbeite config/.env und trage deine API-Keys ein"
echo ""
echo "🚀 2. Starte den Crawler mit:"
echo "   ./start.sh"
echo ""
echo "   Oder manuell:"
echo "   - Einmaliger Crawl:    docker-compose up"
echo "   - Mit Scheduler:       docker-compose --profile scheduler up -d"
echo "   - Logs anzeigen:       docker-compose logs -f"
echo "   - Stoppen:             docker-compose down"
echo ""
echo "📚 Mehr Infos: siehe README.md und DOCKER.md"
