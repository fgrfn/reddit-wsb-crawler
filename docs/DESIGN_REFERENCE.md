# WSB-Crawler — Design-Referenz

Vollständige Referenz für ein UI-Redesign (z. B. in Claude Design). Beschreibt
**Produkt, Screens, Zustände, echte Datenformen (API-Responses) und die aktuell
verwendeten Design-Tokens**. Stand: `main` nach v2.1.0 (inkl. Auth + Signalqualität).

> Alle Response-Beispiele sind die **tatsächlichen** JSON-Formen aus dem Code
> (`api/routers/*`, `runtime/progress.py`, `storage/database.py`). Wer ein Design
> baut, kann Komponenten direkt gegen diese Felder legen.

---

## 1. Produkt in einem Satz

Ein lokal betriebenes **Frühwarnsystem**, das Subreddits (primär r/wallstreetbets)
auf überdurchschnittliche Aktien-**Ticker-Nennungen** überwacht, diese mit Kurs-,
News- und Stimmungs-Daten anreichert und bei Schwellwert-Überschreitung
**Discord-Alerts** sendet. Bedient wird alles über ein **Web-Dashboard**.

**Nutzer:** eine Einzelperson / kleines Team, self-hosted (Docker/NAS/lokal).
**Sprache der Oberfläche:** Deutsch.
**Ton:** sachlich, kompakt, „Tool für Power-User", kein Marketing.

---

## 2. Kern-Workflow (was das Dashboard sichtbar macht)

```
Crawl (Reddit lesen) → Ticker erkennen → Speichern → Spikes analysieren
   → Kurse & News anreichern → Alerts senden → Aufräumen
```

Jeder Crawl durchläuft **8 Phasen** (`steps`, siehe Live-Run unten). Der
Scheduler startet Crawls automatisch im konfigurierten Intervall; zusätzlich
kann man manuell **Live-Lauf** oder **Dry-Run** (crawlt, sendet aber nichts)
auslösen.

**Drei Alert-Typen** (`reason`):

| reason | Bedeutung | Farbe (Akzent) | Label (UI) |
|---|---|---|---|
| `new_ticker` | Ticker war nie da, taucht mit vielen Nennungen auf | Blau `#00B0F4` | „Neu" |
| `spike` | Bekannter Ticker, plötzlicher Anstieg (delta + ratio) | Orange `#FF4500` | „Spike" |
| `price_move` | Spike **und** signifikante Kursbewegung | Amber `#FFAA00` | „Kurs + Aktivität" |

---

## 3. Informationsarchitektur / Navigation

SPA mit Hash-Routing, eine linke Sidebar-Navigation. Seiten:

| Route | Screen | Zweck |
|---|---|---|
| `#setup` | **Setup-Wizard** | Ersteinrichtung (3 Schritte), nur bis konfiguriert |
| `#dashboard` | **Dashboard** | Live-Status, Fortschritt, Top-Ticker, letzte Alerts/Runs |
| `#alerts` | **Alert-History** | Alle gesendeten Alerts, nach Ticker filterbar |
| `#ticker/{SYMBOL}` | **Ticker-Detail** | Verlauf + Alerts eines einzelnen Tickers |
| `#config` | **Konfiguration** | Alle Einstellungen (Secrets maskiert) |
| `#logs` | **Live-Logs** | Echtzeit-Log-Stream (WebSocket) |

Sidebar-Navigationspunkte: Dashboard, Alerts, Config, Logs (Setup nur initial).
Der aktive Punkt ist Reddit-orange hervorgehoben.

---

## 4. Screens im Detail

### 4.1 Setup-Wizard (`#setup`)
3-Schritt-Formular, erscheint solange nicht konfiguriert (`configured=false`).
**Pflichtfelder** (`REQUIRED_SETUP_FIELDS`): `reddit_client_id`,
`reddit_client_secret`, `discord_webhook_url`.
Weitere Felder: `subreddits` (Default-Beispiel `wallstreetbets,wallstreetbetsGER`),
`crawl_interval_minutes` (z. B. `30`).
Zustände: leer, Validierungsfehler, „gespeichert", Abschluss → Weiterleitung Dashboard.

### 4.2 Dashboard (`#dashboard`)
Wichtigster Screen. Von oben nach unten:

1. **Header** mit Titel + Aktionsleiste: Zeitfenster-Umschalter (`7 / 14 / 30 Tage`),
   „Aktualisieren", **„Live-Lauf"** (Primary), **„Dry-Run"** (Ghost).
   Läuft ein Crawl, sind Start-Buttons disabled.
2. **Stat-Tiles** (5 Kacheln): Version · Crawl-Runs · Alerts gesamt · Ticker getrackt · Letzter Lauf
   (jeweils großer Wert + kleine Subzeile).
3. **Run-Fortschritt** (`renderRunProgress`) — nur wenn ein Lauf aktiv/zuletzt:
   Phasenanzeige (8 Steps), Fortschrittsbalken (0–100 %), aktuelle Message,
   Zähler (Posts/Kommentare/Ticker), Pro-Subreddit-Fortschritt.
4. **Diagnostics** (`renderDiagnostics`) — Hinweis-/Fehler-Box (amber), nur wenn vorhanden.
5. **Alert-Vorschau** (`renderAlertPreview`) — Kandidaten des aktuellen Laufs
   mit Confidence-Score + **Sentiment-Badge** (🐂/🐻/➖); nur bei aktivem/letztem Lauf.
6. **Zweispaltig**:
   - **Top-Ticker** (bis 15) als horizontale Balken (Rang, Ticker, Balkenbreite ∝ Nennungen);
     Farbe des Balkens nach Trend (up=grün, down=rot, sonst orange). Klick → Ticker-Detail.
   - **Sidebar**: „Letzte Alerts" (kompakte Alert-Rows) + „Letzte Runs" (OK/Fehler-Status).
7. **Ticker-Tabelle** (voll): Ticker · Nennungen · Ø/Tag · Peak · Trend. Zeilen klickbar.

**Auto-Refresh** während ein Crawl läuft.

### 4.3 Alert-History (`#alerts`)
Filter-Input (Ticker) + Reset. Liste von **Alert-Rows**. Leerzustand: „Noch keine Alerts."
Alert-Row zeigt: `$TICKER` (klickbar), Zeitstempel, Nennungen, Reason-Badge (farbcodiert),
Faktor (`ratio`), Kurs (`price`), Kursänderung (`price_change`, grün/rot).

### 4.4 Ticker-Detail (`#ticker/{SYMBOL}`)
Zeitfenster `7 / 30 / 90 Tage`, „Zurück". Stat-Tiles (Total, Letzter Punkt, Ø, Peak, Trend),
**Mention-Verlauf** als horizontale Balkenliste (Datum + Balken + Wert), **Alerts** dieses Tickers.

### 4.5 Konfiguration (`#config`)
Formular in Sektionen. Secrets sind maskiert (`••••••••`) und werden nur überschrieben,
wenn man neu tippt (leeres Passwortfeld = Wert behalten). Sektionen & Felder:

- **Reddit API:** Client ID, Client Secret*, Reddit Benutzername, Reddit Passwort*, User Agent
- **Discord:** Webhook URL*, Bot Token* (optional)
- **Telegram (optional):** Bot Token*, Chat-ID — zweiter Alert-Kanal parallel zu Discord
- **Subreddits & Crawler:** Subreddits, **Zeitsteuerung** (Umschalter Intervall ↔ Feste Zeiten/Cron: `crawl_interval_minutes` **oder** `cron_expression` + `schedule_mode`), Posts pro Subreddit, Kommentare pro Post
- **Alert-Schwellwerte:** Min. Nennungen neuer Ticker, Min. Anstieg absolut, Min. Faktor,
  Min. Kursänderung %, Max. Alerts pro Lauf, Cooldown Stunden

(`*` = maskiertes Secret-Feld)

### 4.6 Live-Logs (`#logs`)
Voll-Höhe Monospace-Konsole, Auto-Scroll, „Leeren". Zeilen kommen per WebSocket,
Farbe nach Level: ERROR/CRITICAL rot, WARNING amber, „Crawl/fertig" grün, sonst neutral.

---

## 5. API — echte Datenformen

Basis-URL: `/api`. Alles JSON, außer WebSocket. Bei aktiviertem `WSB_AUTH_TOKEN`
verlangen nicht-lokale Requests HTTP-Basic-Auth (Passwort = Token).

### GET `/api/status`  ← Haupt-Polling-Endpunkt des Dashboards
```json
{
  "configured": true,
  "last_run_at": "2026-07-06T14:24:00+00:00",
  "last_run_duration_s": 42.7,
  "total_runs": 128,
  "total_alerts": 17,
  "tracked_tickers": 240,
  "next_run_at": "2026-07-06T14:54:00+00:00",
  "is_healthy": true,
  "crawl_running": false,
  "current_run": { … siehe unten … }
}
```

`current_run` (Live-Fortschritt, `null` wenn noch nie gelaufen):
```json
{
  "run_id": "e5735fcb-…", "short_id": "e5735fcb",
  "active": true, "success": null, "dry_run": false,
  "phase": "enrich", "phase_label": "Kurse & News",
  "message": "Hole Kurse, Namen und News für GME, AMC…",
  "progress": 83,
  "started_at": "…", "updated_at": "…", "finished_at": null, "duration_s": 12.4,
  "subreddits": ["wallstreetbets"],
  "subreddit_progress": {
    "wallstreetbets": { "posts": 100, "comments": 480, "done": true, "error": null }
  },
  "posts_scanned": 100, "comments_scanned": 480, "tickers_found": 240,
  "candidate_count": 4, "active_candidate_count": 2, "alerts_sent": 0,
  "alert_preview": [
    {
      "ticker": "GME", "reason": "spike", "mentions": 40,
      "avg_mentions": 5.0, "ratio": 8.0, "delta": 35, "is_new": false,
      "price": 42.0, "price_change": 2.0, "news_count": 3, "confidence": 86,
      "sentiment": 1.0, "sentiment_label": "bullish", "avg_score": 2250.0
    }
  ],
  "diagnostics": [
    { "at": "…", "level": "INFO", "source": "ticker-quality", "message": "…" }
  ],
  "top_tickers": [ ["GME", 40], ["AMC", 22] ],
  "steps": [
    { "key": "starting", "label": "Start", "done": true },
    { "key": "reddit", "label": "Reddit lesen", "done": true },
    { "key": "extract", "label": "Ticker erkennen", "done": true },
    { "key": "save", "label": "Daten speichern", "done": true },
    { "key": "analysis", "label": "Spikes analysieren", "done": true },
    { "key": "enrich", "label": "Kurse & News", "done": false },
    { "key": "alerts", "label": "Alerts senden", "done": false },
    { "key": "cleanup", "label": "Aufräumen", "done": false }
  ]
}
```
`sentiment_label` ∈ `bullish | bearish | neutral`. `confidence` 0–100. `ratio` kann
`null` sein (neuer Ticker ohne Historie). `progress` 0–100.

### GET `/api/tickers?days=7`  (1–90)
```json
[
  { "ticker": "GME", "total_mentions": 320, "avg_daily": 45.7,
    "peak_mentions": 120, "peak_day": "2026-07-04T00:00:00", "trend": "up",
    "company_name": "GameStop Corp.", "price": 42.0, "price_change": 5.0 }
]
```
`trend` ∈ `up | down | flat` (aus der History berechnet). **`company_name`, `price`,
`price_change` sind „best effort": Dieser Endpunkt wird gepollt und holt daher
**keine** Live-Kurse (Rate-Limit-Schutz) — die Felder sind nur befüllt, wenn der
Ticker im Cache warm ist (z. B. weil er kürzlich ein Alert-Kandidat war), sonst
`null`. Fürs Design: Karten mit Kurs/Name als „anzeigen wenn vorhanden" behandeln.
Der garantiert-frische Kurs kommt aus der Ticker-Detailseite.

### GET `/api/tickers/{ticker}?days=30`
```json
{
  "ticker": "GME", "days": 30,
  "company_name": "GameStop Corp.", "price": 42.0, "price_change": 3.0, "currency": "USD",
  "total_mentions": 320, "latest_mentions": 40,
  "peak_mentions": 120, "avg_mentions": 12.3, "trend": "up",
  "alerts": [ … Alert-Rows (siehe /api/alerts) … ],
  "history": [ { "date": "2026-07-01T00:00:00+00:00", "mentions": 12 } ]
}
```
Hier ist der Kurs **frisch** (einzelner Ticker → kein Burst-Risiko); `price`,
`price_change`, `company_name`, `currency` können `null` sein, wenn yfinance nichts
liefert.

### GET `/api/tickers/{ticker}/history?days=30`
```json
{ "ticker": "GME", "data": [ { "date": "…", "mentions": 12 } ], "avg": 12.3, "trend": "up" }
```

### GET `/api/alerts?limit=50&ticker=GME`  (Alert-History-Rows)
```json
[
  { "id": 42, "ticker": "GME", "reason": "spike", "mentions": 40,
    "avg_mentions": 5.0, "ratio": 8.0, "price": 42.0, "price_change": 2.0,
    "sent_at": "2026-07-06T14:24:00+00:00" }
]
```
> Hinweis: Historische Alert-Rows enthalten **kein** Sentiment/Engagement (nicht
> persistiert). Diese Felder gibt es nur in der Live-`alert_preview` und im Discord-Embed.

### GET `/api/runs?limit=20`  (Crawl-Run-Rows)
```json
[
  { "id": "e5735fcb-…", "started_at": "…", "finished_at": "…",
    "posts_scanned": 100, "comments_scanned": 480,
    "subreddits": "[\"wallstreetbets\"]", "is_healthy": 1 }
]
```
`subreddits` ist ein JSON-**String**; `is_healthy` ist `0/1`.

### GET `/api/mentions/daily?days=14`  (1–90)
Tägliche Gesamt-Nennungen über alle Ticker — Datenquelle für den Übersichts-Flächenchart „Nennungen gesamt".
```json
{ "days": 14, "data": [ { "date": "2026-07-01T00:00:00+00:00", "mentions": 240 } ] }
```

### GET `/api/about`
```json
{ "version": "2.1.0", "build_commit": "e5735fc", "build_date": "2026-07-06" }
```

### GET `/api/config`  → Dict aller Settings, Secrets als `••••••••`
### GET `/api/config/status` → `{ "configured": true }`
### PUT `/api/config`  → `{ "ok": true, "updated": ["subreddits", …] }`
### POST `/api/crawl?dry_run=false` → `{ "ok": true, "dry_run": false }`
&nbsp;&nbsp;&nbsp;&nbsp;Fehler: `400` (unkonfiguriert), `409` (Crawl läuft schon).

### WebSocket `/api/ws/logs`
Server sendet zuerst `__LOGS_CLEAR__`, dann Log-Zeilen im Format
`HH:mm:ss | LEVEL    | message`. Verbindung bleibt offen.

---

## 6. Datenwörterbuch (fachliche Objekte)

| Objekt | Felder (relevant fürs UI) |
|---|---|
| **Ticker (Trend)** | ticker, total_mentions, avg_daily, peak_mentions, peak_day, trend(up/down/flat), company_name, price, price_change |
| **Alert** | ticker, reason(new_ticker/spike/price_move), mentions, avg_mentions, ratio, price, price_change, sent_at |
| **Alert-Preview (live)** | + confidence(0–100), sentiment(-1..1), sentiment_label, avg_score, delta, is_new, news_count |
| **Run** | id, started_at, finished_at, posts_scanned, comments_scanned, subreddits, is_healthy |
| **Live-Run** | phase, phase_label, message, progress, 8×step{key,label,done}, subreddit_progress, Zähler |
| **Diagnostic** | at, level(INFO/WARNING/ERROR), source, message |
| **Status** | configured, last_run_at, last_run_duration_s, total_runs, total_alerts, tracked_tickers, next_run_at, is_healthy, crawl_running |

**Signalqualität (neu):** Jede Alert-Kandidatur trägt ein Sentiment
(`bullish/bearish/neutral`, Zahl -1..1) und ein Engagement (Ø/Peak Post-Score).
Beides fließt in `confidence` und die Reihenfolge der Kandidaten. Der Auslöser
selbst bleibt die reine Nennungszahl.

---

## 7. Aktuelle Design-Tokens (Ist-Zustand, als Ausgangsbasis)

Aktuell: **Dark-Only**, Tailwind (CDN), Font **Inter**, Zinc-Palette + ein
Reddit-oranger Akzent. Für ein Redesign frei austauschbar — hier als Referenz:

**Farben**
| Rolle | Wert |
|---|---|
| Primär-Akzent (Reddit-Orange) | `#FF4500` (hover `#CC3700`) |
| Seiten-Hintergrund | `zinc-950` `#09090B` |
| Karte / Panel | `zinc-900` `#18181B`, Rahmen `zinc-800` `#27272A` |
| Text primär / sekundär / gedämpft | `#F4F4F5` / `#A1A1AA` / `#71717A` |
| Erfolg / Fehler / Warnung | grün `#4ADE80` / rot `#F87171` / amber `#FBBF24` |
| Alert new_ticker / spike / price_move | `#00B0F4` / `#FF4500` / `#FFAA00` |
| Sentiment bullish / bearish / neutral | grün / rot / zinc |

**Form & Typo**
- Karten: radius `1rem`, Padding `1.25rem`, 1px Rahmen.
- Buttons: radius `~0.7rem`, `font-weight 800`; Primary = Orange auf Weiß, Ghost = zinc-800.
- Badges: Pill (`border-radius 999px`), `font-weight 900`, kleine Caps-Labels.
- Zahlen tabellarisch (`tabular-nums`), Ticker in Monospace mit `$`-Präfix.
- Navigations-Aktiv: Orange-Tint-Hintergrund `rgba(255,69,0,.12)` + oranger Text.

**Kernkomponenten, die ein Design abdecken sollte**
Stat-Tile · horizontaler Ranking-Balken · Reason-Badge (3 Farben) ·
Sentiment-Badge (🐂/🐻/➖) · Confidence-Score-Chip · Phasen-/Step-Fortschritt ·
Fortschrittsbalken · Diagnostics-Callout · Alert-Row · Run-Row (OK/Fehler) ·
Daten-Tabelle · Live-Log-Konsole · maskiertes Secret-Feld · Zeitfenster-Umschalter.

**Wichtige Zustände fürs Design**
- **Leer** (noch keine Daten / keine Alerts / keine Historie)
- **Crawl läuft** (Fortschritt sichtbar, Start-Buttons disabled, Auto-Refresh)
- **Dry-Run** (Alerts werden nur als Vorschau angezeigt, nicht gesendet)
- **Fehler** (Diagnostics-Callout, Run als „Fehler", rote Log-Zeilen)
- **Unkonfiguriert** (nur Setup-Wizard erreichbar)

---

## 8. Nicht im UI (Kontext)

- **Discord-Alerts** sind ein separater Ausgabekanal (Rich Embed), kein Screen.
  Das Embed zeigt: Reason-Titel, Erwähnungen, **🧭 Stimmung** (Sentiment + Ø/Peak-Score),
  Kurs (1h/24h/7d), News (bis 3). Farbe = Reason-Farbe.
- **Discord-Bot** (optional) mit Slash-Commands `/top`, `/chart`, `/status`.
- Persistenz komplett in **SQLite**; Konfiguration liegt ebenfalls in der DB
  (keine `.env`).
