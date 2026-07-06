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
- `DB_PATH: Path` — Default `data/wsb_crawler.db` (CWD-relativ, für Docker/systemd); per `WSB_DB_PATH` auf einen absoluten Pfad übersteuerbar (nötig bei systemweiter Installation / Start aus nicht beschreibbarem Verzeichnis)
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
| `crawl_runs` | Crawl-Lauf-History (Start, Ende, Posts/Comments, Status) |
| `ticker_mentions` | Ticker-Nennungen pro Lauf (`run_id`, `ticker`, `mentions`, `recorded_at`) |
| `alert_history` | Gesendete Alerts (Ticker, Grund, Zeitstempel) |
| `alert_cooldowns` | Ticker-Cooldown bis wann kein Alert |
| `settings` | Key/Value-Konfiguration (ersetzt .env) |

Wichtige Methoden:
- `is_configured()` — prüft ob reddit_client_id, reddit_client_secret, discord_webhook_url gesetzt sind
- `get_setting(key)` / `set_setting(key, value)` — Einzel-Zugriff
- `get_all_settings()` — Dict aller Einstellungen
- `get_avg_mentions(ticker, days, exclude_run_id)` / `is_known_ticker(ticker, exclude_run_id)` — für Spike-Erkennung; `exclude_run_id` blendet den gerade gespeicherten Lauf aus
- `get_alert_history(limit, ticker)` — für Dashboard/Alerts-Seite
- `get_recent_runs(limit)` — für Dashboard-Statusanzeige
- `purge_old_mentions(days=90)` — Retention-Cleanup, nach jedem Crawl aufgerufen

---

## API (`api/`)

FastAPI-App mit drei Routern, alle unter `/api/`:

| Router | Endpunkte |
|---|---|
| `config.py` | `GET /api/config` (Secrets maskiert), `PUT /api/config`, `GET /api/config/status` |
| `dashboard.py` | `GET /api/tickers`, `GET /api/tickers/{ticker}/history`, `GET /api/alerts`, `GET /api/runs` |
| `status.py` | `GET /api/status`, `WebSocket /ws/logs` |

**Statische Dateien:** Das Single-File Vanilla-HTML-Dashboard liegt in `src/wsb_crawler/api/static/index.html` und wird unter `/` gemountet. Es wird als Fallback für alle nicht-API-Routen serviert (SPA-Routing per Hash). Kein Build-Step.

**Secret-Maskierung:** `GET /api/config` maskiert `reddit_client_secret`, `reddit_password`, `newsapi_key`, `discord_bot_token`, `discord_webhook_url` und `alphavantage_api_key` mit `••••••••` (Liste in `config.py::SECRET_KEYS`). Die Webhook-URL zählt bewusst dazu — wer sie kennt, kann in den Channel posten.

**DB-Injektion:** `server.py::set_database(db)` setzt das Modul-Level-Attribut `db` in jedem Router vor dem Start.

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

**Bind-Adresse:** Default `127.0.0.1`. `WSB_HOST=0.0.0.0` öffnet den Server fürs LAN (im Docker-Image gesetzt, da fürs Port-Mapping nötig — das Compose-Mapping bindet aber per Default auf `127.0.0.1`). `WSB_NO_BROWSER=1` unterdrückt das automatische Browser-Öffnen (Docker/Headless).

**Authentifizierung (optional):** `WSB_AUTH_TOKEN` aktiviert HTTP-Basic-Auth (`api/auth.py`). Ist das Token gesetzt, verlangt die Middleware in `server.py` für alle nicht-lokalen Requests ein passendes Passwort; Loopback-Clients (127.0.0.1/::1, u. a. Docker-Healthcheck) und `OPTIONS`-Preflights werden durchgelassen. Ohne Token verhält sich der Server wie bisher (offen). Bind auf `0.0.0.0` ohne Token → Startup-Warnung. Die Autorisierungs-Entscheidung liegt seiteneffektfrei in `auth.request_is_authorized()` (unit-getestet in `tests/test_auth.py`).

---

## Bekannte Einschränkungen / TODO

1. **Keine `.env`-Migration:** Wer von v1 migriert, muss Werte manuell im Setup-Wizard eingeben.

2. **Testabdeckung der Entry-Points:** `main.py` und `alerts/bot.py` sind noch ungetestet (Integrations-/Discord-Client-Code). Coverage-Gate liegt bei 60 %.

---

## Konventionen

- **Async überall:** Keine synchronen Blocking-Calls in async-Kontext. `httpx.AsyncClient`, `asyncpraw`, `aiosqlite` — ausnahmslos.
- **Logging:** Nur `loguru`. Kein `print()`, kein `logging.getLogger()`.
- **Fehlerbehandlung:** Auf Top-Level (Scheduler, API-Handlers) abfangen und loggen. In tiefen Funktionen Exceptions durchreichen lassen.
- **Typen:** Pydantic-Modelle für API-Request/Response-Bodies. Dataclasses für interne Konfiguration.
- **Secrets in API-Responses:** Nie im Klartext. `config.py` maskiert die in `SECRET_KEYS` gelisteten Felder (inkl. `discord_webhook_url`) mit `••••••••`.
- **Port:** Default 80, über `WSB_PORT` Environment-Variable änderbar. Port < 1024 benötigt root auf Linux/macOS.
- **Bind:** Default `127.0.0.1`; `WSB_HOST=0.0.0.0` nur bewusst setzen (kein Auth).
- **Datetime:** Immer aware UTC. In der DB-Schicht `_utcnow()`/`_parse_dt()` verwenden, in Modellen `_utcnow()`. Kein `datetime.utcnow()`.
