# Crawl-Intervall Konfiguration

## Übersicht

Der Crawler kann in zwei Modi betrieben werden:

1. **Einmal-Modus** (`wsb-crawler`): Führt einen einzelnen Crawl durch und beendet sich
2. **Scheduler-Modus** (`wsb-crawler-scheduler`): Läuft kontinuierlich mit konfigurierbarem Intervall

**Standard-Intervall: 30 Minuten**

## ⚠️ Wichtig: Unterschied zwischen den Modi

### `wsb-crawler` (Standard-Service)
- ✅ Für **einmalige** Crawls
- ❌ **Kein** automatischer Neustart (`restart: no`)
- ❌ Loop-Modus **deaktiviert**
- 👉 Nutze: `docker-compose up wsb-crawler`

### `wsb-crawler-scheduler` (Scheduler-Service)  
- ✅ Für **regelmäßige** Crawls
- ✅ Automatischer Neustart bei Fehlern (`restart: unless-stopped`)
- ✅ Loop-Modus **aktiviert** mit konfigurierbarem Intervall
- 👉 Nutze: `docker-compose --profile scheduler up -d`

## Konfiguration

### 1. Via Umgebungsvariable (.env)

Füge in `config/.env` hinzu:

```env
CRAWL_INTERVAL_MINUTES=30
```

### 2. Via Docker Compose

Setze die Variable beim Start:

```bash
CRAWL_INTERVAL_MINUTES=60 docker-compose --profile scheduler up -d
```

### 3. Via start.sh Script (EMPFOHLEN)

Das interaktive Start-Script fragt automatisch nach dem Intervall:

```bash
./start.sh
# Wähle Option 2 (Scheduler starten)
# Gib das gewünschte Intervall in Minuten ein (Standard: 30)
```

## Verwendung

### Einmaliger Crawl
```bash
docker-compose up wsb-crawler
# Führt einen Crawl durch und beendet sich
```

### Kontinuierlicher Scheduler
```bash
docker-compose --profile scheduler up -d
# Läuft im Hintergrund mit 30-Minuten-Intervall (oder angepasst)
```

### Scheduler stoppen
```bash
docker-compose --profile scheduler down
```

## Empfohlene Intervalle

- **Testphase**: 5-10 Minuten
- **Normal (empfohlen)**: 30 Minuten  
- **Weniger aktive Zeiten**: 60 Minuten
- **Hoch-frequente Überwachung**: 15 Minuten

## Logs

Überprüfe die Logs, um das aktive Intervall zu sehen:

```bash
# Scheduler-Logs
docker-compose logs -f wsb-crawler-scheduler

# Einmal-Crawl-Logs
docker-compose logs wsb-crawler
```

Bei aktiviertem Scheduler-Modus solltest du sehen:
```
🔄 Scheduler-Modus aktiviert (Intervall: 30 Minuten)
...
⏳ Warte 30 Minuten bis zum nächsten Crawl...
```

## Fehlersuche

**Problem: Crawler läuft sofort nach Beendigung erneut**
- ✅ Lösung: Verwende `--profile scheduler` für kontinuierliche Crawls
- ❌ Nicht verwenden: `docker-compose up wsb-crawler` mit `restart: unless-stopped`

**Problem: Kein Loop-Modus Log sichtbar**  
- Prüfe: `docker-compose logs wsb-crawler-scheduler | grep "Scheduler-Modus"`
- Stelle sicher: `CRAWLER_LOOP_MODE=true` ist gesetzt (im Scheduler-Service standardmäßig aktiv)

