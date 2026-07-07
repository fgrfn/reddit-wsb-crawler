# Changelog

Alle relevanten Änderungen an diesem Projekt werden hier dokumentiert.

## [3.0.0] - 2026-07-07

### Added

- Komplett neu gestaltetes Web-Dashboard (Light-Theme, sechs Screens: Dashboard, Alerts, Ticker-Detail, Konfiguration, Logs, Setup-Wizard) — weiterhin als Single-File ohne Build-Step.
- **Telegram** als optionaler zweiter Alert-Kanal parallel zu Discord (`telegram_bot_token`, `telegram_chat_id`); Alerts gehen an alle konfigurierten Kanäle.
- **Cron-Zeitsteuerung**: feste Uhrzeiten über 5-Feld-Cron (`schedule_mode`, `cron_expression`) alternativ zum festen Intervall, mit abhängigkeitsfreiem Cron-Parser.
- Signalqualität: Engagement-Gewichtung aus Post-Scores und ein Bull/Bear-Sentiment aus dem Nennungs-Kontext fließen in Confidence-Score und Kandidaten-Ranking.
- Sentiment, Confidence und Engagement werden in der Alert-Historie persistiert; Ticker-Detail zeigt Sentiment-Badge und Confidence.
- Optionaler Zugriffsschutz `WSB_AUTH_TOKEN` (HTTP-Basic-Auth) mit Loopback-Ausnahme für den Docker-Healthcheck.
- `GET /api/mentions/daily` für den Übersichts-Flächenchart „Nennungen gesamt".
- Design-Referenz (`docs/DESIGN_REFERENCE.md`) für UI-Arbeit.

### Changed

- Ticker-Endpunkte (`/api/tickers`, `/api/tickers/{ticker}`) liefern jetzt Firmenname, aktuellen Kurs und einen echten (berechneten) Trend statt eines konstanten `flat`; die Liste bleibt netzwerkfrei (cache-only), die Detailseite holt frisch.
- Docker: Port-Mapping bindet standardmäßig auf `127.0.0.1`; bei Bind auf `0.0.0.0` ohne Token wird eine Warnung geloggt.
- Echter Schema-Migrations-Schritt (idempotentes `ALTER TABLE` für fehlende Spalten); `SCHEMA_VERSION` auf 2.
- FastAPI-App liest ihre Version aus `__version__`, damit sie nicht mehr driftet.

### Removed

- Toter `build-frontend`-Workflow (verwies auf ein nicht vorhandenes `web/`-Verzeichnis).

## [2.1.0] - 2026-07-06

### Added

- Live-Run-Status im Dashboard mit Phase, Fortschritt, Laufzeit, Schritt-Liste, Subreddit-Zählern, Top-Tickern und Alert-Metriken.
- `current_run` im `/api/status` Endpoint für den aktuellen oder zuletzt abgeschlossenen Crawl.
- In-memory Runtime-Progress-Tracker für lange Crawl-Läufe.
- Detailliertere INFO-Logs während Reddit-Crawling, Ticker-Extraktion, Spike-Analyse, Preis-/News-Enrichment und Alert-Versand.
- Docker Healthcheck gegen `/api/status`.
- Dashboard-Version und Build-Metadaten über `/api/about`.
- Dry-Run-Modus für manuell gestartete Crawls ohne Discord-Versand oder Cooldown-Schreibzugriffe.
- Alert-Vorschau mit Confidence Score, Mention-Daten, Preisänderung und News-Anzahl im Live-Run-Status.
- Diagnosebereich im Dashboard für Warnungen und Fehler während eines Crawls.
- Ticker-Detailseite mit Mention-Verlauf und Alert-Historie.

### Changed

- Ticker-Erkennung reduziert False Positives durch strengere Behandlung impliziter Großbuchstaben-Ticker ohne `$`.
- yfinance/Yahoo-Enrichment wird gedrosselt, dedupliziert und nutzt einen negativen Runtime-Cache für fehlgeschlagene Kursabfragen.
- Fehlgeschlagene yfinance-Kursabfragen laufen jetzt nach TTL aus, statt bis zum Container-Neustart blockiert zu bleiben.
- Neue, unsichere Drei-Buchstaben-Ticker werden vor Discord-Alerts zusätzlich qualitätsgeprüft.
- Konfigurationsstatus berücksichtigt jetzt sowohl SQLite-Settings als auch Docker/Unraid-ENV-Overrides.
- Docker-Start korrigiert Besitzrechte von `/app/data` und `/app/logs` und unterstützt `PUID`/`PGID`.
- README für Release-Betrieb auf `main`, Version `2.1.0`, Docker/Unraid und Live-Dashboard aktualisiert.

### Fixed

- SQLite `unable to open database file` bei bind-mounted Docker-/Unraid-Volumes mit falschen Host-Rechten.
- Leere Startseite vor abgeschlossenem Setup durch Redirect auf `/setup`.
- Scheduler wartete trotz gültiger ENV-Konfiguration auf Dashboard-Setup.
- Manuelle Crawls konnten trotz unvollständiger Konfiguration gestartet werden.
- Wiederholte Yahoo/yfinance `429 Too Many Requests` durch Burst-Anfragen und doppelte Kursabfragen.
- Häufige False-Positive-Alerts aus normalen Wörtern/Abkürzungen wie `USA`, `USD`, `WEN`, `LMAO`, `ROI`, `RAM`, `DRAM`.
- FastAPI-Start-Crash durch Response-Type-Inferenz bei SPA-Routen.

### Notes

- `asyncpraw==7.8.1` bleibt für dieses Release gepinnt. Ein Upgrade auf `asyncpraw 8.x` sollte separat getestet werden, da es ein Major-Update ist.
- Das Live-Progress-Tracking ist bewusst runtime-only und wird nicht historisch persistiert.

## [2.0.0]

### Added

- Async Reddit-Crawling mit `asyncpraw`.
- SQLite-basierte History statt Pickle-Dateien.
- FastAPI Dashboard mit Setup-Wizard, Konfiguration, Alert-Historie und Live-Logs.
- Discord Webhook-Alerts und optionale Slash-Commands.
- pytest/ruff/mypy-basierte CI.
