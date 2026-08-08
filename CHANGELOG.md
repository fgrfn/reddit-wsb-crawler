# Changelog

Alle relevanten Änderungen an diesem Projekt werden hier dokumentiert.

## [Unreleased]

### Added

- **Erfolgskontrolle für Alerts**: Zu jedem Alert wird der Kurs 1 h und 24 h später nachgemessen (am Ende jedes Crawls, gedrosselt und ohne den Lauf gefährden zu können). Die Alerts-Seite zeigt daraus je Alert-Grund Durchschnitts-Entwicklung und Trefferquote — Schwellwerte lassen sich damit anhand von Daten statt nach Gefühl justieren. Neuer Endpunkt `GET /api/alerts/stats`.
- **Schwellwert-Simulator**: `GET /api/alerts/simulate` spielt die gespeicherte Historie mit anderen Schwellwerten durch und zeigt sofort, wie viele Alerts dabei entstanden wären (inkl. Cooldown und Limit pro Lauf). In der Alerts-Seite als Formular mit Ergebnis-Übersicht. Bewusst eine Näherung: Kurs-/News-Anreicherung wird nicht simuliert.
- **Ticker-Filter in der WebUI** (Sektion „Ticker-Filter“): eigene Wörter zusätzlich ignorieren (Fehlalarme selbst abstellen) und Ausnahmen von der eingebauten Blacklist erlauben (echte Ticker, die als normales Wort gefiltert werden, z.B. WEN für Wendy’s). Bisher war die Blacklist nur im Code änderbar. Eigene Einträge greifen auch bei $-Schreibweise; bei widersprüchlicher Angabe gewinnt die Ausnahme.
- **Alphavantage als Zweitquelle für Kurse**: Liefert Yahoo keinen Kurs (Drosselung mit `429` oder „no price data found"), wird — falls ein Schlüssel konfiguriert ist — Alphavantage befragt. Meldet auch diese API ihr Limit, wird der Fallback vorübergehend gesperrt, statt das Tageskontingent zu verbrennen.
- Alphavantage- und NewsAPI-Schlüssel sind jetzt in der WebUI eintragbar (neue Sektion „Datenquellen"); bisher waren sie nur per ENV oder direktem API-Aufruf setzbar. Der Alphavantage-Schlüssel war zuvor überhaupt nicht ausgewertet.

### Fixed

- Ein einzelnes fehlendes yfinance-Feld ließ den kompletten Kursabruf scheitern (`Konnte Kurs für HTZ nicht holen: 'currency'`), obwohl der Preis vorhanden war — Felder werden jetzt defensiv gelesen.
- Bei `429 Too Many Requests` wurde die Anfrage wiederholt und die Drosselung damit verschärft; Rate-Limits werden jetzt erkannt, nicht wiederholt und führen direkt zur Zweitquelle. Sie erscheinen außerdem nicht mehr als Warnung, weil sie Betriebsrauschen sind.

### Added

- Die Discord-Testnachricht sendet jetzt einen **erfundenen Beispiel-Alert**, gerendert über denselben Code wie echte Alerts — man sieht damit sofort, wie ein Alert aussieht, statt nur eine Erfolgsmeldung zu bekommen. Deutlich als Test gekennzeichnet und bewusst ohne Ping; die konfigurierten @-Ziele werden nur benannt.
- **Velocity-Frühwarnung**: neuer Alert-Grund `velocity`, der die Nennungen des aktuellen Laufs gegen den Schnitt der letzten Läufe vergleicht (Default: 3 Läufe, Faktor 2.5, min. 8 Nennungen; in der WebUI ein-/ausschaltbar). Damit werden Spikes erkannt, **während sie aufbauen** — der 30-Tage-Schnitt reagiert dafür zu spät. Fehlende Läufe zählen als 0, ein voller Vergleich braucht Historie, und der Rauschfilter verhindert Alarme bei Kleinstzahlen. Beschleunigung fließt in Confidence und Kandidaten-Ranking ein und wird in Discord-/Telegram-Alerts sowie im Dashboard ausgewiesen.

- Der Crawler liest jetzt mehrere Reddit-Listings pro Lauf (`hot`, `new`, `rising`, `top`; Default `hot,new,rising`, wählbar in der WebUI unter „Reddit-Quellen"). `new`/`rising` zeigen aufkommende Ticker, bevor sie in `hot` auftauchen — Spikes werden dadurch früher erkannt. Posts werden über die Listings dedupliziert, und `posts_limit` bleibt die Gesamt-Obergrenze pro Subreddit (gleichmäßig auf die Quellen verteilt), sodass die API-Last unverändert bleibt.

## [3.1.1] - 2026-08-07

### Added

- Discord-Alerts können konfigurierte User/Rollen per `@` erwähnen (`discord_mention_targets`, einstellbar in der WebUI). Unterstützt User-IDs, Rollen (`&<id>`/`role:<id>`), `@here` und `@everyone`; der Ping wird mit passenden `allowed_mentions` gesetzt, damit er zuverlässig ausgelöst wird.

### Changed

- Die Paketversion wird jetzt aus dem Git-Tag abgeleitet (hatch-vcs, `dynamic = ["version"]`); `__version__` liest sie aus den Paket-Metadaten. Damit entfällt das manuelle Nachziehen der Versionsnummer an mehreren Stellen — die Versions-Drift ist strukturell behoben. Der Release-Prozess ist nur noch: CHANGELOG-Eintrag → mergen → `vX.Y.Z` taggen.

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
