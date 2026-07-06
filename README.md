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
| Dashboard | keins | FastAPI + Vanilla HTML/CSS/JS (localhost:80) |
| Setup | manuelle `.env` Bearbeitung | Setup-Wizard im Browser |
| Docker | 2 Services, Profile-Flag | 1 Service, Port 80 |
| Tests | test_logging.py | pytest + pytest-asyncio, ~65% Coverage |
| Dependencies | ungepinnt | vollständig gepinnt in pyproject.toml |

---

## Quick Start

### Voraussetzungen

- Python 3.11+
- Reddit-App: [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
- Discord Webhook-URL

### Setup-Script (empfohlen)

Das Setup-Script installiert alle Abhängigkeiten und richtet optional einen Autostart-Service ein:

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

# 3. Starten
wsb-crawler
```

Der Browser öffnet sich automatisch. Beim ersten Start wird der Setup-Wizard angezeigt.

### Docker

```bash
git clone -b dev https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

docker compose up -d
# Dashboard: http://localhost
```

> **Hinweis:** Port 80 erfordert unter Linux/macOS ggf. sudo. Alternativ Port ändern: `WSB_PORT=8080 docker compose up`
>
> **Docker-Volumes:** Die SQLite-Datenbank liegt im Container unter `/app/data/wsb_crawler.db` und wird per `./data:/app/data` persistent gespeichert. Der Container startet kurz als root, korrigiert die Besitzerrechte von `/app/data` und `/app/logs`, und führt die App danach als Non-Root-User `crawler` aus. Standard ist `PUID=1000` / `PGID=1000`. Auf Unraid ist häufig `PUID=99 PGID=100` passend:
>
> ```bash
> PUID=99 PGID=100 docker compose up -d
> ```
>
> **Sicherheit:** Das Dashboard hat **keine Authentifizierung**. Bei lokalem Start bindet es daher nur auf `127.0.0.1`. Für Zugriff aus dem LAN (z. B. NAS/Server) `WSB_HOST=0.0.0.0` setzen — dann ist es für alle im Netzwerk erreichbar (im Docker-Image ist das bereits gesetzt, weil das Port-Mapping es benötigt). In diesem Fall den Container besser nur an ein vertrauenswürdiges Interface mappen, z. B. `127.0.0.1:80:80`.

---

## Konfiguration

Alle Einstellungen werden über das Web-Dashboard unter **http://localhost** gesetzt — keine `.env`-Datei nötig.

> **Port ändern:** Setze die Umgebungsvariable `WSB_PORT=8080` vor dem Start, falls Port 80 nicht verfügbar ist.
>
> **Datenbank-Pfad:** Standardmäßig wird die DB unter `data/wsb_crawler.db` **relativ zum Arbeitsverzeichnis** angelegt. Im Docker-Image ist explizit `WSB_DB_PATH=/app/data/wsb_crawler.db` gesetzt. Wer das Paket systemweit installiert und aus einem beliebigen — evtl. nicht beschreibbaren — Verzeichnis startet, setzt einen absoluten Pfad: `WSB_DB_PATH=~/.local/share/wsb-crawler/wsb.db`. Andernfalls kann es zu `unable to open database file` kommen.

### Erster Start — Setup-Wizard

Beim ersten Start (keine Konfiguration in der DB) öffnet sich automatisch der Setup-Wizard unter `http://localhost/setup`.

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

## Updates einspielen

```bash
bash update.sh
```

Das Script zieht die neuesten Commits, aktualisiert Python-Abhängigkeiten im Venv und startet den Service neu.

---



Das Dashboard ist unter **http://localhost** erreichbar (nur lokal, keine Authentifizierung nötig).

| Seite | Inhalt |
|---|---|
| Dashboard | Crawler-Status, Top-Ticker-Chart, Mention-Tabelle |
| Alerts | Alert-Historie mit Ticker-Filter |
| Konfiguration | Alle Einstellungen bearbeiten und speichern |
| Logs | Live-Logstream via WebSocket |

---

## Port-Konfiguration

**Standard:** Port 80 (http://localhost)

**Port ändern:**

```bash
# Lokal / Setup-Script
WSB_PORT=8080 wsb-crawler
WSB_PORT=8080 python setup.py

# Docker
WSB_PORT=8080 docker compose up -d

# Persistent (Docker)
echo "WSB_PORT=8080" > .env
docker compose up -d
```

> **Hinweis:** Port < 1024 erfordert unter Linux/macOS root-Rechte (`sudo`).

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
```

### Branch-Strategie

```
main        ← Stable Releases (Tags)
dev         ← aktive Entwicklung
feature/xyz ← Feature-Branches → PR nach dev
```

---

## Projektstruktur
