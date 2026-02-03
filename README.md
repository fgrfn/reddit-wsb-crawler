<div align="center">

<img src="logo.png" alt="WSB-Crawler Logo" width="300"/>


[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/fgrfn/reddit-wsb-crawler/releases)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://github.com/fgrfn/reddit-wsb-crawler/pkgs/container/reddit-wsb-crawler)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF.svg)](https://github.com/fgrfn/reddit-wsb-crawler/actions)

**Automatisches Frühwarnsystem für Reddit-Aktien-Hypes**

Crawlt r/wallstreetbets nach Ticker-Erwähnungen, analysiert Trends und sendet Discord-Alerts bei ungewöhnlicher Aktivität.

[Features](#-features) • [Quick Start](#-quick-start) • [Docker](#-docker) • [Konfiguration](#-konfiguration) • [Dokumentation](#-dokumentation)

</div>

---

## ✨ Features

### 🔍 **Intelligentes Crawling**
- Durchsucht konfigurierbare Subreddits (wallstreetbets, wallstreetbetsGER, etc.)
- Regex-basierte Ticker-Erkennung in Posts & Kommentaren
- Parallel-Processing für schnelle Analyse
- Deduplizierung und Blacklist-Filter

### 📊 **Umfassende Datenanalyse**
- **Kursdaten**: Live-Kurse + Pre/After-Market von Yahoo Finance
- **Trend-Analyse**: 1h, 24h, 7d Kursveränderungen
- **News-Integration**: Aktuelle Headlines via NewsAPI
- **Historischer Vergleich**: Erkennt signifikante Anstiege

### 🔔 **Smart Alerts**
- **Discord Rich Embeds** mit Farbcodierung und strukturierten Feldern
- Benachrichtigungen bei ungewöhnlicher Aktivität
- Konfigurierbare Schwellwerte (Nennungen, Kursänderungen)
- Kompaktes Format mit klickbaren Links
- Silent Status-Updates (Heartbeat ohne Ping)

### 🐳 **Production-Ready**
- Vollständige Docker-Unterstützung
- Automatische Releases via GitHub Actions
- Semantic Versioning mit Auto-Increment
- Persistente Daten & Caching

## 🚀 Quick Start

### Option 1: Docker (empfohlen) 🐳

```bash
# 1. Repository klonen
git clone https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

# 2. Config erstellen
cp config/.env.example config/.env
nano config/.env  # API-Keys eintragen (siehe unten)

# 3. Interaktives Start-Script verwenden
./start.sh
# → Wähle Option 2 (Scheduler starten)
# → Gib Intervall ein (Standard: 30 Minuten)

# Oder manuell starten:
# Einmaliger Crawl
docker-compose up

# Scheduler mit 30-Min-Intervall (empfohlen)
CRAWL_INTERVAL_MINUTES=30 docker-compose --profile scheduler up -d

# 4. Logs anschauen
docker-compose logs -f wsb-crawler-scheduler
```

**Oder Pre-built Image nutzen:**

```bash
# Latest Version von GitHub Container Registry
docker pull ghcr.io/fgrfn/reddit-wsb-crawler:latest

# Mit spezifischer Version für Reproduzierbarkeit
docker pull ghcr.io/fgrfn/reddit-wsb-crawler:v1.3.0
```

### Option 2: Python (lokal)

```bash
# 1. Repository klonen
git clone https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

# 2. Virtual Environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Dependencies installieren
pip install -r requirements.txt

# 4. Config erstellen
cp config/.env.example config/.env
nano config/.env  # API-Keys eintragen

# 5. Crawler starten
python src/run_crawler_headless.py
```

---

## ⚙️ Konfiguration

#### Erforderliche Credentials:

| Variable | Beschreibung | Wo bekomme ich das? |
|----------|--------------|---------------------|
| `REDDIT_CLIENT_ID` | Reddit API Client ID | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |
| `REDDIT_CLIENT_SECRET` | Reddit API Secret | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |
| `REDDIT_USER_AGENT` | User Agent String | z.B. `python:wsb-crawler:v1.0.0 (by /u/your_username)` |
| `NEWSAPI_KEY` | NewsAPI Key | [newsapi.org/register](https://newsapi.org/register) |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL | Discord Server Settings → Integrations → Webhooks |

#### Optionale Einstellungen:

```ini
# Subreddits (komma-separiert)
SUBREDDITS=wallstreetbets,wallstreetbetsGER,mauerstrassenwetten

# News-Einstellungen
NEWSAPI_LANG=en           # Sprache für News (en, de, etc.)
NEWSAPI_WINDOW_HOURS=48   # Zeitfenster für News in Stunden

---

## 📱 Discord-Nachrichten

Der Crawler sendet zwei Arten von Nachrichten:

### 1. 🔔 Alert-Nachricht (bei ungewöhnlicher Aktivität)

Wird als **neue Nachricht** gepostet und pingt alle:

```
⚠️ WSB-ALARM — Ungewöhnliche Aktivität entdeckt
💾 260203-012557_crawler-ergebnis.pkl
⏰ 03.02.2026 01:28:28

🥇 AMD - Advanced Micro Devices Inc 🚨
🔢 Nennungen: 28 (Δ +18)
💵 89.45 USD (+2.34 USD, +2.69%) 📈 [03.02.2026 01:28] 
    | 🌅 Pre-Market: 89.12 USD | Status: REGULAR 
    | Trends: 1h ▲ +1.2% · 24h ▲ +2.8% · 7d ▲ +5.3% 
    | https://finance.yahoo.com/quote/AMD
🧠 AMD zeigt starke Performance nach positiven Q4-Zahlen...
📰 AMD Reports Record Revenue: Q4 Earnings Beat Expectations (Reuters) | https://...
📰 AI Chip Demand Drives AMD Stock Surge (Bloomberg) | https://...
---
🥈 PLTR - Palantir Technologies Inc
🔢 Nennungen: 22 (Δ +15)
💵 35.67 USD (-0.89 USD, -2.44%) 📉 [03.02.2026 01:28]
    | 🌙 After-Market: 35.45 USD | Status: POST 
    | Trends: 1h ▼ -0.5% · 24h ▼ -2.1% · 7d ▲ +8.7%
    | https://finance.yahoo.com/quote/PLTR
🧠 Palantir secured new government contracts worth $450M...
---
```

### 2. 🟢 Status-Nachricht (Heartbeat)

Wird **kontinuierlich editiert** (kein Ping, kein Spam!):

```
💚 **WSB-Crawler Status**
🕐 Letzter Crawl: 03.02.2026 01:28:28 (vor 2 Minuten)
📊 Posts überprüft: 200
🔔 Alerts ausgelöst: 2

⏭️ Nächster Crawl: 03.02.2026 01:58:28

**Top 5 Erwähnungen:**
1. AMD: 28
2. PLTR: 22
3. LINK: 15
4. NVDA: 12
5. TSLA: 9

🆔 Run-ID: `260203-012557`
```

> 💡 **Tipp:** Die Status-Nachricht wird alle 30 Minuten aktualisiert (editiert), 
> sodass du **nur eine Nachricht** im Channel hast, die sich automatisch aktualisiert!

### Alert-Bedingungen

Ein Alert wird ausgelöst, wenn:

- **Neue Ticker:** ≥ 20 Nennungen (konfigurierbar: `ALERT_MIN_ABS`)
- **Bekannte Ticker:** 
  - Anstieg ≥ 10 Nennungen (`ALERT_MIN_DELTA`)
  - **UND** ≥ 200% des vorherigen Werts (`ALERT_RATIO`)
- Optional: Kursveränderung ≥ 5% (`ALERT_MIN_PRICE_MOVE`)

Pro Crawl werden max. 3 Alerts gesendet (`ALERT_MAX_PER_RUN`) mit 4h Cooldown pro Ticker (`ALERT_COOLDOWN_H`)

---

## 🐳 Docker

### Pre-built Images

Das Projekt stellt automatisch gebaute Docker Images bereit:

| Tag | Beschreibung | Verwendung |
|-----|--------------|------------|
| `latest` | Neueste Version vom main branch | Empfohlen für Production |
| `v1.0.1` | Spezifische Release-Version | Für Reproduzierbarkeit |
| `v1.0` | Minor-Version (automatisch) | Latest Patch einer Minor-Version |

```bash
# Latest Version
docker pull ghcr.io/fgrfn/reddit-wsb-crawler:latest
docker run --env-file config/.env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  ghcr.io/fgrfn/reddit-wsb-crawler:latest

# Spezifische Version für Reproduzierbarkeit
docker pull ghcr.io/fgrfn/reddit-wsb-crawler:v1.0.1
```

### Docker Compose (empfohlen)

Das Repo enthält ein vollständiges `docker-compose.yml` mit allen Konfigurationen.

**1. Einmalig ausführen:**
```bash
# Mit lokalem Build
docker-compose up

# Mit Pre-built Image
docker-compose -f docker-compose.prod.yml up
```

**2. Mit Scheduler (regelmäßige Crawls):**
```bash
# Führt Crawler im Intervall aus (Standard: alle 60 Minuten)
docker-compose --profile scheduler up -d

# Logs anschauen
docker-compose logs -f wsb-crawler-scheduler

# Intervall anpassen (z.B. 15 Minuten)
CRAWL_INTERVAL=900 docker-compose --profile scheduler up -d
```

**3. Beispiel `docker-compose.prod.yml`:**
```yaml
version: '3.8'

services:
  wsb-crawler:
    image: ghcr.io/fgrfn/reddit-wsb-crawler:latest
    container_name: wsb-crawler
    restart: unless-stopped
    
    environment:
      - TZ=Europe/Berlin
    
    env_file:
      - config/.env
    
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config/.env:/app/config/.env:ro
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Erforderliche Environment-Variablen

Erstelle `config/.env` mit folgenden Variablen:

**Pflicht-Felder:**
```bash
# Reddit API (https://www.reddit.com/prefs/apps)
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=python:wsb-crawler:v1.0.0 (by /u/yourusername)

# NewsAPI (https://newsapi.org/register)
NEWSAPI_KEY=your_newsapi_key_here

# Discord Webhook
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL
```

**Optional (mit Defaults):**
```bash
# Subreddits (komma-separiert)
SUBREDDITS=wallstreetbets,wallstreetbetsGER

# News-Einstellungen
NEWSAPI_LANG=en                # Sprache (en, de, fr, etc.)
NEWSAPI_WINDOW_HOURS=48        # Zeitfenster für News

# Discord Status-Updates
DISCORD_STATUS_UPDATE=true     # Silent Status (ohne @everyone)

# Alert-Schwellwerte
ALERT_MIN_ABS=20              # Min. Nennungen für neue Ticker
ALERT_MIN_DELTA=10            # Min. Anstieg für bekannte Ticker
ALERT_RATIO=2.0               # Min. Faktor (200% des Vorwerts)
ALERT_MIN_PRICE_MOVE=5.0      # Min. Kursänderung in %
ALERT_MAX_PER_RUN=3           # Max. Alerts pro Crawl
ALERT_COOLDOWN_H=4            # Cooldown pro Ticker in Stunden

# Scheduler (nur für --profile scheduler)
CRAWL_INTERVAL=3600           # Intervall in Sekunden (60 Min.)
```

Vollständige Vorlage: [`config/.env.example`](config/.env.example)

Mehr Details: [DOCKER.md](DOCKER.md)

---

## 📊 Monitoring & Logs

### Logs ansehen

```bash
# Docker
docker-compose logs -f
docker-compose logs --tail=50 wsb-crawler

# Lokal
tail -f logs/crawler.log
```

### Log-Dateien

- `logs/crawler.log` - Hauptlog
- `logs/resolver.log` - Ticker-Namensauflösung
- `logs/openai_costs.log` - API-Kosten (falls verwendet)
- `logs/archive/` - Archivierte Logs

---

## 📝 License

MIT License - siehe [LICENSE](LICENSE)

---

<div align="center">

**Entwickelt mit ❤️ für die WSB-Community**

⭐ Wenn dir dieses Projekt gefällt, gib uns einen Star!

[⬆ Nach oben](#-wsb-crawler)

</div>







