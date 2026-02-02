#!/bin/bash
# Quick setup script for WSB-Crawler

set -e

echo "🚀 WSB-Crawler Setup"
echo "===================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker ist nicht installiert. Bitte installiere Docker erst:"
    echo "   https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose ist nicht installiert. Bitte installiere Docker Compose erst:"
    echo "   https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker gefunden"
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
echo "1. Einmaliger Test-Crawl:"
echo "   docker-compose up"
echo ""
echo "2. Mit Scheduler (stündliche Crawls im Hintergrund):"
echo "   docker-compose --profile scheduler up -d"
echo ""
echo "3. Logs anzeigen:"
echo "   docker-compose logs -f"
echo ""
echo "4. Stoppen:"
echo "   docker-compose down"
echo ""
echo "📚 Mehr Infos: siehe DOCKER.md"
