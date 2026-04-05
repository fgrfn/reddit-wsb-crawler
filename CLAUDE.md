# CLAUDE.md — WSB-Crawler v2

Dieses Dokument beschreibt Architektur, Konventionen und bekannte Eigenheiten des Projekts für KI-Assistenten und neue Entwickler.

---

## Projektübersicht

WSB-Crawler v2 ist ein lokal betriebenes Frühwarnsystem, das Subreddits (primär r/wallstreetbets) auf überdurchschnittliche Ticker-Nennungen überwacht und bei Schwellwert-Überschreitung Discord-Alerts sendet.

**Stack:**
- Python 3.11+, async/await durchgehend
- aiosqlite (SQLite) für alle persistenten Daten inkl. Konfiguration
- FastAPI + uvicorn als interner API-Server (Port 80, via ENV änderbar)
- Vanilla HTML/CSS/JS + Tailwind CSS (CDN) als Web-Dashboard — kein Build-Step
- loguru für Logging, asyncpraw für Reddit, discord.py für Bot/Webhooks

---

## Build & Run

```bash
# Python-Abhängigkeiten installieren (editable, inkl. dev)
pip install -e ".[dev]"

# Anwendung starten (Browser öffnet sich automatisch)
wsb-crawler

# Alternativ: Komplett-Setup inkl. Autostart-Option
python setup.py
```

**Tests:**
```bash
pytest                        # alle Tests + Coverage-Report
pytest tests/test_models.py   # einzelnes Modul
ruff check src/ tests/        # Linting
ruff format src/ tests/       # Formatierung
mypy src/                     # Typ-Check
```

---

## Architektur

### Startup-Ablauf (`main.py`)

```
main()
  └── main_async()
        ├── Database(DB_PATH) öffnen / initialisieren
        ├── webbrowser.open() → /setup wenn unkonfiguriert, sonst /
        └── asyncio.gather()
              ├── run_server(db)       ← FastAPI auf :80 (oder WSB_PORT)
              ├── scheduler_loop(db)   ← Crawl-Scheduler
              └── discord_bot (optional, nur wenn bot_token gesetzt)
```

### Scheduler-Loop

1. Pollt `db.is_configured()` alle 5 Sekunden — wartet auf Setup-Wizard-Abschluss
2. Nach Konfiguration: regelmäßige `run_single_crawl(db)` Aufrufe
3. Intervall wird nach jedem Lauf neu aus DB geladen (Dashboard-Änderungen wirken sofort)

### Datenpfad pro Crawl

```
crawl_all_subreddits()
  → asyncpraw: Posts + Comments aus konfigurierten Subreddits
  → ticker.py: Regex-Erkennung, Blacklist-Filterung
  → DB: Mentions speichern (save_run_mentions)

analyze_mentions()
  → detector.py: Spike-Erkennung (absolut + relativ + Kurs)
  → prices.py: yfinance für Kursdaten
  → news.py: NewsAPI für Schlagzeilen
  → resolver.py: Ticker → Firmenname

send_alerts()
  → discord.py: Rich Embed via Webhook
  → DB: Cooldown setzen, Alert speichern
```

---

## Konfiguration

**Keine `.env`-Datei.** Alle Einstellungen liegen in der SQLite-DB in der Tabelle `settings` (key/value).

`config.py` stellt bereit:
- `DB_PATH: Path` — hardcoded `data/wsb_crawler.db`
- `async get_settings(db: Database) -> Settings` — liest alle Werte aus DB, wirft `RuntimeError` wenn Pflichtfelder fehlen

Die `Settings`-Dataclass enthält:
- `reddit: RedditSettings` (client_id, client_secret, user_agent)
- `discord: DiscordSettings` (webhook_url, bot_token, channel_id)
- `alerts: AlertSettings` (min_abs, min_delta, ratio, min_price_move, max_per_run, cooldown_h)
- `crawler: CrawlerSettings` (subreddits, crawl_interval_minutes)

**Wichtig:** `get_settings(db)` hat keinen Cache — wird vor jedem Crawl frisch geladen, damit Dashboard-Änderungen sofort wirken.

---

## Datenbank (`storage/database.py`)

SQLite-Datei: `data/wsb_crawler.db`

| Tabelle | Inhalt |
|---|---|
| `runs` | Crawl-Lauf-History (Start, Ende, Posts/Comments, Status) |
| `mentions` | Ticker-Nennungen pro Lauf |
| `alerts` | Gesendete Alerts (Ticker, Grund, Zeitstempel) |
| `cooldowns` | Ticker-Cooldown bis wann kein Alert |
| `settings` | Key/Value-Konfiguration (ersetzt .env) |

Wichtige Methoden:
- `is_configured()` — prüft ob reddit_client_id, reddit_client_secret, discord_webhook_url gesetzt sind
- `get_setting(key)` / `set_setting(key, value)` — Einzel-Zugriff
- `get_all_settings()` — Dict aller Einstellungen
- `get_alert_history(limit, ticker)` — für Dashboard/Alerts-Seite
- `get_recent_runs(limit)` — für Dashboard-Statusanzeige

---

## API (`api/`)

FastAPI-App mit drei Routern, alle unter `/api/`:

| Router | Endpunkte |
|---|---|
| `config.py` | `GET /api/config` (Secrets maskiert), `PUT /api/config`, `GET /api/config/status` |
| `dashboard.py` | `GET /api/tickers`, `GET /api/tickers/{ticker}/history`, `GET /api/alerts`, `GET /api/runs` |
| `status.py` | `GET /api/status`, `WebSocket /ws/logs` |

**Statische Dateien:** React-Build liegt in `src/wsb_crawler/api/static/` und wird unter `/` gemountet. Die Datei `index.html` wird als Fallback für alle nicht-API-Routen serviert (SPA-Routing).

**DB-Injektion:** `server.py::set_database(db)` setzt ein Modul-Level `_db` in jedem Router vor dem Start.

**Log-WebSocket:** `status.py` installiert einen loguru-Sink, der alle Lognachrichten in eine `deque(maxlen=200)` schreibt und an alle verbundenen WebSocket-Clients broadcasted.

---

## Frontend

**Single-File HTML Dashboard** in `src/wsb_crawler/api/static/index.html`:
- Vanilla HTML/CSS/JS — kein Build-Step, kein Node.js erforderlich
- Tailwind CSS per CDN
- Hash-basiertes Routing (SPA-ähnlich)
- 5 Seiten: Setup (3-Schritt-Wizard), Dashboard, Alerts, Config, Logs
- Live-Logs via WebSocket (`/api/ws/logs`)
- Auto-Refresh während Crawl läuft

Das Dashboard ist direkt im Repo committed und funktioniert ohne Build-Vorgang.

---

## Docker

`docker-compose.yml` hat nur noch einen Service (`wsb-crawler`), der Port 80 exponiert. Kein `env_file`, kein Scheduler-Profile — der Scheduler läuft intern als asyncio-Task.

```bash
docker compose up -d
# Dashboard: http://localhost
```

**Port ändern:** Setze `WSB_PORT=8080` als Environment-Variable oder in `.env`-Datei.

---

## Bekannte Einschränkungen / TODO

1. **`datetime.utcnow()` Deprecation:** In `models.py` verwenden `PriceData.fetched_at` und `Alert.triggered_at` noch `datetime.utcnow` als `default_factory`. Ab Python 3.12 erzeugt das DeprecationWarnings. Fix: `lambda: datetime.now(tz=timezone.utc)` — erfordert aber Überprüfung aller datetime-Vergleiche (naiv vs. aware) in DB-Code.

2. **Keine `.env`-Migration:** Wer von v1 migriert, muss Werte manuell im Setup-Wizard eingeben.

---

## Konventionen

- **Async überall:** Keine synchronen Blocking-Calls in async-Kontext. `httpx.AsyncClient`, `asyncpraw`, `aiosqlite` — ausnahmslos.
- **Logging:** Nur `loguru`. Kein `print()`, kein `logging.getLogger()`.
- **Fehlerbehandlung:** Auf Top-Level (Scheduler, API-Handlers) abfangen und loggen. In tiefen Funktionen Exceptions durchreichen lassen.
- **Typen:** Pydantic-Modelle für API-Request/Response-Bodies. Dataclasses für interne Konfiguration.
- **Secrets in API-Responses:** Nie im Klartext. `config.py` Router maskiert alle `*_secret`, `*_token`, `*_key` Felder mit `••••••••`.
- **Port:** Default 80, über `WSB_PORT` Environment-Variable änderbar. Port < 1024 benötigt root auf Linux/macOS.
