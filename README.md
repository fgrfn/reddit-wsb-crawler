# WSB-Crawler v2

[![CI](https://github.com/fgrfn/reddit-wsb-crawler/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/fgrfn/reddit-wsb-crawler/actions)
[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/fgrfn/reddit-wsb-crawler/releases)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Automatisches Frühwarnsystem für Reddit-Aktien-Hypes — async, mit Web-Dashboard, SQLite-History und Discord-Alerts.

Der Crawler überwacht konfigurierbare Subreddits (z. B. r/wallstreetbets) auf ungewöhnliche Häufungen von Ticker-Nennungen und sendet bei Schwellwert-Überschreitung sofort Discord-Alerts. Konfiguration, Monitoring und Historie sind über ein modernes Browser-Dashboard erreichbar — keine `.env`-Dateien nötig.

---

## Was ist neu in v2?

| Feature | v1 | v2 |
|---|---|---|
| Reddit-Crawling | sync (praw) | async (asyncpraw) |
| API-Calls | sequentiell | parallel (asyncio.gather) |
| State | Pickle-Dateien | SQLite (querybar) |
| Config | `.env`-Datei | Web-Dashboard (SQLite-backed) |
| Logging | colorama + pyfiglet + halo | loguru + Live-Log im Browser |
| Discord | nur Webhooks | Webhooks + Slash-Commands (/top, /chart, /status) |
| Dashboard | keins | FastAPI + React/Vite (localhost:8080) |
| Setup | manuelle `.env` Bearbeitung | Setup-Wizard im Browser |
| Docker | 2 Services, Profile-Flag | 1 Service, Port 8080 |
| Tests | test_logging.py | pytest + pytest-asyncio, >70% Coverage |
| Dependencies | ungepinnt | vollständig gepinnt in pyproject.toml |

---

## Quick Start

### Voraussetzungen

- Python 3.11+
- Node.js 18+ (nur zum Bauen des Frontends nötig)
- Reddit-App: [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
- Discord Webhook-URL

### Setup-Script (empfohlen)

Das Setup-Script installiert alle Abhängigkeiten, baut das Frontend und richtet optional einen Autostart-Service ein:

```bash
git clone -b dev https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

python setup.py
```

Das Script fragt interaktiv, ob ein Autostart-Service eingerichtet werden soll (Windows Task Scheduler / Linux systemd / macOS launchd).

### Manuell (lokal)

```bash
# 1. Repository klonen
git clone -b dev https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

# 2. Python-Abhängigkeiten installieren
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# 3. Frontend bauen
cd web
npm install
npm run build
cd ..

# 4. Starten
wsb-crawler
```

Der Browser öffnet sich automatisch. Beim ersten Start wird der Setup-Wizard angezeigt.

### Docker

```bash
git clone -b dev https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

docker compose up -d
# Dashboard: http://localhost:8080
```

---

## Konfiguration

Alle Einstellungen werden über das Web-Dashboard unter **http://localhost:8080** gesetzt — keine `.env`-Datei nötig.

### Erster Start — Setup-Wizard

Beim ersten Start (keine Konfiguration in der DB) öffnet sich automatisch der Setup-Wizard unter `http://localhost:8080/setup`.

**Schritt 1 — Reddit API**

| Feld | Beschreibung | Link |
|---|---|---|
| Client ID | Reddit App Client ID | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |
| Client Secret | Reddit App Secret | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |
| User Agent | Frei wählbar, z. B. `wsb-crawler/2.0` | — |

**Schritt 2 — Discord**

| Feld | Beschreibung |
|---|---|
| Webhook URL | Discord → Servereinstellungen → Integrationen → Webhooks |
| Bot Token | Optional — aktiviert Slash-Commands |
| Channel ID | Optional — Kanal für Slash-Commands |

**Schritt 3 — Crawler**

| Feld | Standard | Beschreibung |
|---|---|---|
| Subreddits | `wallstreetbets` | Kommagetrennte Liste |
| Intervall | `30` Min | Crawl-Häufigkeit |
| Alert-Schwellwerte | s. u. | Wann ein Alert ausgelöst wird |

### Alert-Schwellwerte

| Einstellung | Standard | Beschreibung |
|---|---|---|
| Min. Nennungen (neu) | 20 | Mindest-Nennungen für unbekannte Ticker |
| Min. Anstieg (abs.) | 10 | Absoluter Anstieg ggü. letztem Lauf |
| Anstiegsfaktor | 2.0 | Faktor ggü. historischem Durchschnitt |
| Min. Kursbewegung | 5 % | Mindest-Kursveränderung |
| Max. Alerts pro Lauf | 3 | Begrenzung pro Crawl |
| Cooldown | 4 h | Wartezeit pro Ticker zwischen Alerts |

---

## Web-Dashboard

Das Dashboard ist unter **http://localhost:8080** erreichbar (nur lokal, keine Authentifizierung nötig).

| Seite | Inhalt |
|---|---|
| Dashboard | Crawler-Status, Top-Ticker-Chart, Mention-Tabelle |
| Alerts | Alert-Historie mit Ticker-Filter |
| Konfiguration | Alle Einstellungen bearbeiten und speichern |
| Logs | Live-Logstream via WebSocket |

---

## Discord Slash-Commands

Erfordert einen konfigurierten Discord Bot Token (optional).

| Command | Beschreibung |
|---|---|
| `/top [days]` | Top-10-Ticker der letzten N Tage (Standard: 7) |
| `/chart <ticker> [days]` | Mention-Verlauf als ASCII-Chart (Standard: 30 Tage) |
| `/status` | Letzter Crawl, Laufzeit, Alerts gesamt |

---

## Entwicklung

```bash
# Tests ausführen
pytest

# Linting
ruff check src/ tests/

# Formatierung
ruff format src/ tests/

# Typ-Check
mypy src/

# Frontend (Dev-Server mit Hot-Reload, proxied nach :8080)
cd web
npm run dev
```

### Branch-Strategie

```
main        ← Stable Releases (Tags)
dev         ← aktive Entwicklung
feature/xyz ← Feature-Branches → PR nach dev
```

---

## Projektstruktur

```
reddit-wsb-crawler/
├── setup.py                    # Installations- & Autostart-Script
├── pyproject.toml
├── docker-compose.yml
├── web/                        # React/Vite Frontend
│   ├── src/
│   │   ├── pages/              # Dashboard, Alerts, Config, Logs, Setup
│   │   └── components/         # Layout
│   └── vite.config.ts          # Build → src/wsb_crawler/api/static/
└── src/wsb_crawler/
    ├── config.py               # Dataclasses + async get_settings(db)
    ├── models.py               # Typisierte Datenstrukturen
    ├── main.py                 # Entry Point: API-Server + Scheduler
    ├── api/
    │   ├── server.py           # FastAPI-App, statische Dateien
    │   └── routers/
    │       ├── config.py       # GET/PUT /api/config
    │       ├── dashboard.py    # /api/tickers, /api/alerts, /api/runs
    │       └── status.py       # /api/status, WebSocket /ws/logs
    ├── crawler/
    │   ├── reddit.py           # Async Reddit-Crawling (asyncpraw)
    │   └── ticker.py           # Regex-Erkennung + Blacklist
    ├── enrichment/
    │   ├── prices.py           # Kursdaten (yfinance)
    │   ├── news.py             # Headlines (NewsAPI)
    │   └── resolver.py         # Ticker → Firmenname
    ├── analysis/
    │   ├── detector.py         # Spike-Erkennung
    │   └── trends.py           # Trend-Analyse
    ├── alerts/
    │   ├── discord.py          # Rich Embeds + Heartbeat
    │   └── bot.py              # Discord Slash-Commands
    └── storage/
        ├── database.py         # SQLite via aiosqlite (inkl. settings-Tabelle)
        └── cache.py            # In-Memory TTL-Cache
```

---

## License

MIT — siehe [LICENSE](LICENSE)
