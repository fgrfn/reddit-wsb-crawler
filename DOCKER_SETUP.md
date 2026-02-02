# 🐳 Docker-Setup auf Unraid

## Behobene Probleme

Die folgenden Fehler wurden behoben:

### ✅ 1. Fehlende NYSE- und DE/EU-Ticker-Listen
**Problem:** Warnungen "Keine NYSE-Liste gefunden" und "Keine DE/EU-Liste gefunden"

**Lösung:** Die Listen sind jetzt optional. Der Crawler funktioniert auch nur mit NASDAQ-Daten.

**Optional - Vollständige Ticker-Listen hinzufügen:**

Wenn du auch NYSE und europäische Aktien tracken möchtest:

1. **NYSE-Liste herunterladen:**
   ```bash
   # In deinem Unraid Docker data/input Verzeichnis
   wget https://datahub.io/core/nyse-other-listings/r/nyse-listed.csv -O nyse-listed-symbols.csv
   ```

2. **DE/EU-Liste (optional):**
   - Datei von [Deutsche Börse](https://www.deutsche-boerse.com/dbg-de/ueber-uns/services/know-your-market/listen-statistiken) herunterladen
   - Als `de-listed-symbols.xlsx` im `data/input/` Verzeichnis speichern

### ✅ 2. systemctl-Fehler in Docker
**Problem:** `[Errno 2] No such file or directory: 'systemctl'`

**Lösung:** Der Code erkennt jetzt automatisch Docker-Umgebungen und zeigt "unbekannt (Docker)" für den nächsten Crawl-Zeitpunkt.

### ✅ 3. Discord-Benachrichtigungs-Fehler
**Problem:** `ERROR: Fehler bei der Discord-Benachrichtigung: 'Kurs'`

**Lösung:** Kursdaten-Zugriff wurde abgesichert. Kurse werden jetzt separat nach der Aggregation geladen.

## Verzeichnisstruktur für Docker

Stelle sicher, dass folgende Verzeichnisse gemappt sind:

```
/mnt/user/appdata/reddit-wsb-crawler/
├── config/              # Konfigurationsdateien
│   └── .env            # API-Keys und Einstellungen
├── data/
│   ├── input/          # Ticker-Listen (optional: NYSE, DE/EU)
│   │   └── .gitkeep
│   ├── output/         # Crawl-Ergebnisse
│   │   └── pickle/     # Pickle-Dateien mit Treffer-Daten
│   └── state/          # Status-Daten
└── logs/               # Log-Dateien
```

## Docker-Compose Beispiel für Unraid

```yaml
version: '3.8'

services:
  reddit-wsb-crawler:
    image: dein-image:latest
    container_name: reddit-wsb-crawler
    restart: unless-stopped
    environment:
      - TZ=Europe/Berlin
    volumes:
      - /mnt/user/appdata/reddit-wsb-crawler/config:/workspaces/reddit-wsb-crawler/config
      - /mnt/user/appdata/reddit-wsb-crawler/data:/workspaces/reddit-wsb-crawler/data
      - /mnt/user/appdata/reddit-wsb-crawler/logs:/workspaces/reddit-wsb-crawler/logs
```

## Umgebungsvariablen (.env)

Die `.env`-Datei im `config/` Verzeichnis sollte folgende Variablen enthalten:

```bash
# Reddit API
REDDIT_CLIENT_ID=dein_client_id
REDDIT_CLIENT_SECRET=dein_secret
REDDIT_USER_AGENT="WSB Crawler by u/deinusername"

# Discord Webhook
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# OpenAI (für Zusammenfassungen)
OPENAI_API_KEY=sk-...

# Alpha Vantage (optional, für Ticker-Auflösung)
ALPHA_VANTAGE_API_KEY=dein_key

# Discord User IDs (optional, für Benachrichtigungen)
ADMIN_DISCORD_USER_IDS=123456789,987654321
```

## Erste Schritte

1. **Verzeichnisse erstellen:**
   ```bash
   mkdir -p /mnt/user/appdata/reddit-wsb-crawler/{config,data/{input,output,state},logs}
   ```

2. **`.env`-Datei erstellen:**
   ```bash
   nano /mnt/user/appdata/reddit-wsb-crawler/config/.env
   # Füge deine API-Keys ein
   ```

3. **Container starten:**
   - In Unraid: Docker-Tab → Add Container
   - Oder via Docker Compose

4. **Logs überprüfen:**
   ```bash
   docker logs -f reddit-wsb-crawler
   ```

## Hinweise

- **NASDAQ-Liste:** Wird automatisch online geladen (keine Aktion nötig)
- **NYSE/DE-EU-Listen:** Optional - nur wenn du diese Märkte auch tracken möchtest
- **systemd-Timer:** Funktioniert nicht in Docker - nutze stattdessen Cron oder Docker-eigene Scheduler
- **Speicherplatz:** Stelle sicher, dass genug Platz für Logs und Pickle-Dateien vorhanden ist

## Troubleshooting

### Keine Crawl-Ergebnisse
```bash
# Prüfe, ob Reddit API-Keys korrekt sind
docker exec -it reddit-wsb-crawler cat config/.env | grep REDDIT
```

### Discord-Benachrichtigung funktioniert nicht
```bash
# Teste Webhook manuell
curl -X POST -H "Content-Type: application/json" \
  -d '{"content":"Test"}' \
  https://discord.com/api/webhooks/DEINE_WEBHOOK_URL
```

### Container startet nicht
```bash
# Prüfe Logs
docker logs reddit-wsb-crawler

# Prüfe Berechtigungen
ls -la /mnt/user/appdata/reddit-wsb-crawler/
```
