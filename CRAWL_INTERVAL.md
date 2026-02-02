# Crawl-Intervall Konfiguration

## Übersicht

Der Crawler kann nun mit einem konfigurierbaren Intervall betrieben werden. Das Standard-Intervall beträgt **30 Minuten**.

## Konfiguration

### 1. Via Umgebungsvariable (.env)

Füge in `config/.env` hinzu:

```env
CRAWL_INTERVAL_MINUTES=30
```

### 2. Via Docker Compose

Setze die Variable beim Start:

```bash
CRAWL_INTERVAL_MINUTES=60 docker-compose up
```

### 3. Via start.sh Script

Das interaktive Start-Script fragt automatisch nach dem Intervall:

```bash
./start.sh
# Wähle Option 2 (Scheduler starten)
# Gib das gewünschte Intervall in Minuten ein (Standard: 30)
```

## Modi

### Einmaliger Crawl (ohne Loop)
```bash
# Führt einen einzelnen Crawl durch und beendet sich dann
docker-compose up wsb-crawler
```

### Scheduler-Modus (mit Loop)
```bash
# Führt Crawls in regelmäßigen Abständen durch
docker-compose --profile scheduler up -d
```

Der Hauptcontainer (`wsb-crawler`) ist nun auch mit Loop-Modus aktiviert, sodass er kontinuierlich im konfigurierten Intervall crawlt.

## Empfohlene Intervalle

- **Testphase**: 5-10 Minuten
- **Normal**: 30 Minuten
- **Weniger aktive Zeiten**: 60 Minuten

## Logs

Überprüfe die Logs, um das aktive Intervall zu sehen:

```bash
docker-compose logs -f wsb-crawler
```

Du solltest sehen:
```
🔄 Scheduler-Modus aktiviert (Intervall: 30 Minuten)
...
⏳ Warte 30 Minuten bis zum nächsten Crawl...
```
