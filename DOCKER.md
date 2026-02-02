# 🐳 Docker Setup für WSB-Crawler

## Schnellstart

### 1. Konfiguration vorbereiten

Erstelle `config/.env` mit deinen Credentials:

```bash
cp config/.env.example config/.env
# Bearbeite config/.env mit deinen API-Keys
```

### 2. Build & Run

**Einmaliger Crawl:**
```bash
docker-compose up --build
```

**Mit Scheduler (stündliche Crawls):**
```bash
docker-compose --profile scheduler up -d wsb-crawler-scheduler
```

**Development Mode:**
```bash
docker-compose -f docker-compose.dev.yml up -d
docker exec -it wsb-crawler-dev bash
```

## Docker Commands

### Build
```bash
# Image bauen
docker-compose build

# Ohne Cache bauen
docker-compose build --no-cache
```

### Run
```bash
# Im Vordergrund
docker-compose up

# Im Hintergrund
docker-compose up -d

# Mit Scheduler
docker-compose --profile scheduler up -d
```

### Logs
```bash
# Logs anzeigen
docker-compose logs -f

# Nur Crawler-Logs
docker-compose logs -f wsb-crawler

# Letzte 50 Zeilen
docker-compose logs --tail=50 wsb-crawler
```

### Stop & Clean
```bash
# Container stoppen
docker-compose down

# Container + Volumes löschen
docker-compose down -v

# Alles löschen (inkl. Images)
docker-compose down -v --rmi all
```

## Scheduler-Konfiguration

Der Scheduler führt Crawls in konfigurierbaren Intervallen aus:

```bash
# 30 Minuten
CRAWL_INTERVAL=1800 docker-compose --profile scheduler up -d

# 2 Stunden
CRAWL_INTERVAL=7200 docker-compose --profile scheduler up -d
```

## Volume-Management

### Persistente Daten

Daten werden in lokalen Verzeichnissen gespeichert:
- `./data/` - Pickle-Files, Caches, Ticker-Listen
- `./logs/` - Log-Files

### Volumes prüfen
```bash
docker volume ls
docker volume inspect wsb-crawler_wsb-data
```

### Daten sichern
```bash
# Backup erstellen
docker run --rm -v $(pwd)/data:/data -v $(pwd)/backup:/backup \
  alpine tar czf /backup/wsb-data-$(date +%Y%m%d).tar.gz -C /data .

# Backup wiederherstellen
docker run --rm -v $(pwd)/data:/data -v $(pwd)/backup:/backup \
  alpine tar xzf /backup/wsb-data-YYYYMMDD.tar.gz -C /data
```

## GitHub Container Registry

Nach jedem Release wird automatisch ein Docker-Image gebaut:

```bash
# Image pullen
docker pull ghcr.io/fgrfn/reddit-wsb-crawler:latest

# Spezifische Version
docker pull ghcr.io/fgrfn/reddit-wsb-crawler:v1.0.0

# Mit gepulltem Image laufen lassen
docker run --rm \
  --env-file config/.env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  ghcr.io/fgrfn/reddit-wsb-crawler:latest
```

## Troubleshooting

### Container startet nicht
```bash
# Logs prüfen
docker-compose logs wsb-crawler

# Container-Status prüfen
docker-compose ps
```

### Permissions-Probleme
```bash
# Data/Logs Verzeichnisse berechtigen
chmod -R 755 data logs
```

### Memory-Issues
```bash
# Ressourcen-Limits in docker-compose.yml anpassen
deploy:
  resources:
    limits:
      memory: 4G  # erhöhen
```

### Netzwerk-Probleme
```bash
# DNS prüfen
docker-compose exec wsb-crawler ping -c 3 google.com

# Reddit API testen
docker-compose exec wsb-crawler python -c "import praw; print('OK')"
```

## Production Setup

### Mit systemd (empfohlen)

Erstelle `/etc/systemd/system/wsb-crawler.service`:

```ini
[Unit]
Description=WSB Crawler Container
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/path/to/reddit-wsb-crawler
ExecStart=/usr/bin/docker-compose --profile scheduler up -d
ExecStop=/usr/bin/docker-compose down
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Aktivieren:
```bash
sudo systemctl enable wsb-crawler
sudo systemctl start wsb-crawler
```

### Mit systemd Timer

Timer-File `/etc/systemd/system/wsb-crawler.timer`:

```ini
[Unit]
Description=WSB Crawler Timer
Requires=wsb-crawler.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Unit=wsb-crawler.service

[Install]
WantedBy=timers.target
```

## Monitoring

### Container-Stats
```bash
# Ressourcen-Nutzung
docker stats wsb-crawler

# Prozesse im Container
docker-compose exec wsb-crawler ps aux
```

### Health-Checks
```bash
# Health-Status prüfen
docker inspect --format='{{.State.Health.Status}}' wsb-crawler
```

### Log-Rotation
Konfiguriert in `docker-compose.yml`:
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

## Best Practices

1. **Secrets Management**: Nutze Docker Secrets für Produktion
2. **Updates**: Regelmäßig Images aktualisieren
3. **Backups**: Automatische Backups von `./data` einrichten
4. **Monitoring**: Log-Aggregation (z.B. ELK Stack) nutzen
5. **Resources**: Limits für CPU/Memory setzen
