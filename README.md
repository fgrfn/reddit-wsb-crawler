# WSB-Crawler v2

[![CI](https://github.com/fgrfn/reddit-wsb-crawler/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fgrfn/reddit-wsb-crawler/actions)
[![Version](https://img.shields.io/badge/version-2.1.0-blue)](https://github.com/fgrfn/reddit-wsb-crawler/releases)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Automatisches Frühwarnsystem für Reddit-Aktien-Hypes — async, mit Web-Dashboard, SQLite-History und Discord-Alerts.

Der Crawler überwacht konfigurierbare Subreddits, z. B. `wallstreetbets` und `wallstreetbetsGER`, auf ungewöhnliche Häufungen von Ticker-Nennungen. Bei Schwellwert-Überschreitung sendet er Discord-Alerts. Konfiguration, Live-Fortschritt, Logs, Historie und Ticker-Auswertungen laufen über ein Browser-Dashboard.

---

## Highlights in v2.1.0

- Live-Run-Status im Dashboard: aktuelle Phase, Fortschritt, Laufzeit, Posts, Kommentare, Ticker, Kandidaten, Alerts und Subreddit-Fortschritt.
- Detailliertere Logs während langer Crawls: Reddit-Lesen, Ticker-Erkennung, Spike-Analyse, Kurs-/News-Enrichment und Alert-Versand.
- Weniger False Positives bei Ticker-Erkennung: reine Großbuchstaben-Wörter und häufige Reddit-/Makro-Abkürzungen werden strenger gefiltert.
- yfinance/Yahoo-Enrichment wird gedrosselt und dedupliziert, um `429 Too Many Requests` deutlich zu reduzieren.
- Docker-Volume-Rechte für `/app/data` und `/app/logs` werden beim Start korrigiert, inklusive `PUID`/`PGID` für Unraid.
- Konsistenter Konfigurationsstatus: DB-Settings und Docker/Unraid-ENV-Variablen werden gleichermaßen berücksichtigt.

---

## Quick Start

### Voraussetzungen

- Python 3.11+
- Reddit-App: [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
- Discord Webhook-URL

### Docker

```bash
git clone https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

docker compose up -d --build
# Dashboard: http://localhost
```

> **Hinweis:** Port 80 erfordert unter Linux/macOS ggf. root-Rechte. Alternativ Port ändern:
>
> ```bash
> WSB_PORT=8080 docker compose up -d --build
> ```

### Unraid-Hinweise

- Docker-Netzwerk bevorzugt: **Bridge**, nicht Host, wenn du Port-Mapping nutzen willst.
- Bei Unraid sind häufig `PUID=99` und `PGID=100` passend:

```bash
PUID=99 PGID=100 docker compose up -d --build
```

Die SQLite-Datenbank liegt im Container unter `/app/data/wsb_crawler.db` und wird per `./data:/app/data` persistent gespeichert. Der Container startet kurz als root, korrigiert die Besitzerrechte von `/app/data` und `/app/logs`, und führt die App danach als Non-Root-User `crawler` aus.

### Manuell lokal

```bash
git clone https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"

wsb-crawler
```

Der Browser öffnet sich automatisch. Beim ersten Start wird der Setup-Wizard angezeigt.

---

## Konfiguration

Alle Einstellungen können über das Web-Dashboard gesetzt werden. Pflichtfelder für den ersten Start:

| Feld | Beschreibung |
|---|---|
| Reddit Client ID | Reddit-App Client ID |
| Reddit Client Secret | Reddit-App Secret |
| Discord Webhook URL | Discord Webhook für Alerts |

Optional können Werte auch per Environment gesetzt werden. ENV-Variablen haben Vorrang vor DB-Werten, z. B.:

```bash
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
DISCORD_WEBHOOK_URL=...
WSB_DB_PATH=/app/data/wsb_crawler.db
WSB_PORT=8080
WSB_AUTH_TOKEN=ein-langes-geheimnis   # optional, siehe unten
```

> **Sicherheit:** Ohne `WSB_AUTH_TOKEN` hat das Dashboard keine Authentifizierung. Bei lokalem Start bindet es standardmäßig nur auf `127.0.0.1`, und `docker compose` published den Port ebenfalls nur auf `127.0.0.1` (nur der Docker-Host erreicht das Dashboard).
>
> **Für LAN-/Remote-Zugriff** (z. B. NAS): setze `WSB_AUTH_TOKEN=<geheim>` und öffne das Port-Mapping in `docker-compose.yml`. Ist ein Token gesetzt, verlangt der Server für alle nicht-lokalen Zugriffe HTTP-Basic-Auth (Benutzername beliebig, Passwort = Token); Loopback-Zugriffe (u. a. der Docker-Healthcheck) bleiben ohne Token erlaubt. Bindet der Server auf `0.0.0.0` **ohne** Token, wird beim Start eine deutliche Warnung geloggt.

---

## Dashboard

| Seite | Inhalt |
|---|---|
| Dashboard | Live-Run-Status, Fortschritt, Top-Ticker, letzte Alerts und letzte Runs |
| Alerts | Alert-Historie mit Ticker-Filter |
| Konfiguration | Alle Einstellungen bearbeiten und speichern |
| Logs | Live-Logstream via WebSocket |

Während eines laufenden Crawls zeigt das Dashboard die aktuellen Schritte:

```text
Reddit lesen → Ticker erkennen → Daten speichern → Spikes analysieren → Kurse & News → Alerts senden → Aufräumen
```

Dazu kommen Live-Zähler für Posts, Kommentare, erkannte Ticker, Spike-Kandidaten und gesendete Alerts.

---

## Alert-Schwellwerte

| Einstellung | Standard | Beschreibung |
|---|---:|---|
| Min. Nennungen neuer Ticker | 20 | Mindest-Nennungen für unbekannte Ticker |
| Min. Anstieg absolut | 10 | Absoluter Anstieg gegenüber historischer Basis |
| Anstiegsfaktor | 2.0 | Faktor gegenüber historischem Durchschnitt |
| Min. Kursbewegung | 5 % | Mindest-Kursveränderung für Price-Move-Alerts |
| Max. Alerts pro Lauf | 3 | Begrenzung pro Crawl |
| Cooldown | 4 h | Wartezeit pro Ticker zwischen Alerts |

---

## Discord Slash-Commands

Erfordert einen konfigurierten Discord Bot Token. Der Webhook allein reicht für normale Alerts.

| Command | Beschreibung |
|---|---|
| `/top [days]` | Top-10-Ticker der letzten N Tage, Standard: 7 |
| `/chart <ticker> [days]` | Mention-Verlauf als ASCII-Chart, Standard: 30 Tage |
| `/status` | Letzter Crawl, Laufzeit, Alerts gesamt |

---

## Updates einspielen

```bash
# Docker
git pull
docker compose up -d --build

# Lokale Installation
bash update.sh
```

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

```text
main        ← Stable Releases + Tags
dev         ← aktive Entwicklung
feature/xyz ← Feature-Branches → PR nach dev/main
```

---

## Projektstruktur

```text
src/wsb_crawler/
  api/          FastAPI-Router + statisches Dashboard
  alerts/       Discord Webhooks und Bot-Commands
  analysis/     Spike-/Alert-Erkennung
  crawler/      Reddit-Crawler und Ticker-Extraktion
  enrichment/   Kurs-, News- und Namens-Enrichment
  runtime/      In-memory Live-Run-Status
  storage/      SQLite-Datenbank und Cache
```
