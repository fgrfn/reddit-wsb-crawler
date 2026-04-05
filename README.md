# WSB-Crawler v2

[![CI](https://github.com/fgrfn/reddit-wsb-crawler/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/fgrfn/reddit-wsb-crawler/actions)
[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/fgrfn/reddit-wsb-crawler/releases)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Automatisches Frühwarnsystem für Reddit-Aktien-Hypes — jetzt vollständig async, mit SQLite-History und Discord Slash-Commands.

---

## Was ist neu in v2?

| Feature | v1 | v2 |
|---|---|---|
| Reddit-Crawling | sync (praw) | async (asyncpraw) |
| API-Calls | sequentiell | parallel (asyncio.gather) |
| State | Pickle-Dateien | SQLite (querybar) |
| Config | os.getenv() überall | Pydantic Settings (validiert beim Start) |
| Logging | colorama + pyfiglet + halo | loguru (ein Package) |
| Discord | nur Webhooks | Webhooks + Slash-Commands (/top, /chart, /status) |
| Docker | 2 Services, 80 Zeilen Duplikation | YAML Anchors, Multi-Stage, Non-Root |
| Tests | test_logging.py | pytest + pytest-asyncio, >70% Coverage |
| Dependencies | ungepinnt | vollständig gepinnt in pyproject.toml |

---

## Quick Start

### Docker (empfohlen)

```bash
# 1. Repository klonen (dev branch)
git clone -b dev https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

# 2. Config anlegen
cp config/.env.example config/.env
nano config/.env   # API-Keys eintragen

# 3. Einmaliger Crawl
docker compose up

# 4. Dauerbetrieb (alle 30 Min)
docker compose --profile scheduler up -d

# 5. Logs
docker compose logs -f wsb-crawler-scheduler
```

### Lokal (Python)

```bash
# 1. Python 3.11+ und pip vorausgesetzt
git clone -b dev https://github.com/fgrfn/reddit-wsb-crawler.git
cd reddit-wsb-crawler

# 2. Virtual Environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Installieren (inkl. Dev-Tools)
pip install -e ".[dev]"

# 4. Config
cp config/.env.example config/.env
nano config/.env

# 5. Starten
wsb-crawler
```

---

## Konfiguration

Alle Einstellungen in `config/.env`. Fehlende Pflichtfelder → sofortiger Abbruch mit klarer Fehlermeldung.

### Pflichtfelder

| Variable | Beschreibung | Link |
|---|---|---|
| `REDDIT_CLIENT_ID` | Reddit App Client ID | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |
| `REDDIT_CLIENT_SECRET` | Reddit App Secret | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |
| `NEWSAPI_KEY` | NewsAPI Key | [newsapi.org/register](https://newsapi.org/register) |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL | Discord → Servereinstellungen → Integrationen |

### Optional: Discord Bot (Slash-Commands)

```env
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_COMMAND_CHANNEL_ID=123456789
```

Aktiviert `/top`, `/chart` und `/status` direkt in Discord.

### Alert-Schwellwerte

```env
ALERT_MIN_ABS=20        # Min. Nennungen für neue Ticker
ALERT_MIN_DELTA=10      # Min. absoluter Anstieg (bekannte Ticker)
ALERT_RATIO=2.0         # Min. Faktor ggü. historischem Durchschnitt
ALERT_MIN_PRICE_MOVE=5  # Min. Kursveränderung in %
ALERT_MAX_PER_RUN=3     # Max. Alerts pro Crawl
ALERT_COOLDOWN_H=4      # Cooldown pro Ticker in Stunden
```

---

## Discord Slash-Commands

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
main  ← Stable Releases (Tags)
dev   ← aktive Entwicklung
feature/xyz ← Feature-Branches → PR nach dev
```

---

## Projektstruktur

```
src/wsb_crawler/
├── config.py          # Pydantic Settings
├── models.py          # Typisierte Datenstrukturen
├── crawler/
│   ├── reddit.py      # Async Reddit-Crawling
│   └── ticker.py      # Regex-Erkennung + Blacklist
├── enrichment/
│   ├── prices.py      # Kursdaten (yfinance)
│   ├── news.py        # Headlines (NewsAPI)
│   └── resolver.py    # Ticker → Firmenname
├── analysis/
│   ├── detector.py    # Spike-Erkennung
│   └── trends.py      # Trend-Analyse (für /top, /chart)
├── alerts/
│   ├── discord.py     # Rich Embeds + Heartbeat
│   └── bot.py         # Discord Slash-Commands
├── storage/
│   ├── database.py    # SQLite via aiosqlite
│   └── cache.py       # In-Memory TTL-Cache
└── main.py            # Entry Point + Scheduler
```

---

## License

MIT — siehe [LICENSE](LICENSE)
