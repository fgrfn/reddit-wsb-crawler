# WSB-Crawler

Leichter Reddit‑Crawler für r/wallstreetbets (inkl. DE‑Subreddit).  
Sammelt Ticker‑Erwähnungen, identifiziert relevante Kandidaten, holt Kursdaten (yfinance) und Headlines (NewsAPI) und sendet kompakte Discord‑Alarme mit Kurs, Trends und News.

## Kurzüberblick
- Ziel: Frühwarnungen bei plötzlichen Diskussions‑/Kursbewegungen (z. B. mögliche Short‑Squeezes).
- Ergebnis: Pickle‑Outputs, kurze Text‑Summaries und Discord‑Alerts (Webhook).

## Hauptfunktionen
- Zählt Ticker‑Erwähnungen in konfigurierbaren Subreddits
- Holt Kursdaten (yfinance) inkl. Pre/After‑Market und Trendkennzahlen (1h/24h/7d)
- Ruft Headlines ausschließlich über NewsAPI ab (NEWSAPI_KEY erforderlich)
- Erzeugt lokale Kurz‑Zusammenfassungen und speichert sie
- Sende‑Mechanismus: Discord Webhook (Alert‑Format optimiert für schnelle Übersicht)

## Voraussetzungen
- Python 3.9+
- Abhängigkeiten:
```bash
pip install -r requirements.txt
```

## Konfiguration
Lege `config/.env` im Repo‑Root an (empfohlen). Minimales Beispiel:
```ini
# Reddit
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=python:wsb-crawler:v1.0 (by /u/you)
SUBREDDITS=wallstreetbets,wallstreetbetsGER

# NewsAPI (erforderlich für Headlines)
NEWSAPI_KEY=dein_newsapi_key
NEWSAPI_LANG=en
NEWSAPI_WINDOW_HOURS=48

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Alert thresholds (Beispiele)
ALERT_MIN_ABS=20
ALERT_MIN_DELTA=10
ALERT_RATIO=2.0
ALERT_MIN_PRICE_MOVE=5.0
ALERT_MAX_PER_RUN=3
ALERT_COOLDOWN_H=4
```
Hinweis: `config/.env` (Repo‑Root) wird bevorzugt; es gibt Fallbacks (`src/config/.env`, `./config/.env`).

## Schnellstart / Befehle
- Voller Headless‑Crawl:
```bash
python src/run_crawler_headless.py
```
- Lokale Discord‑Preview (nutzt neueste Pickle):
```bash
python src/scripts/test_discord_message.py --use-real
```
- Preview + senden (benötigt gültigen `DISCORD_WEBHOOK_URL`):
```bash
python src/scripts/test_discord_message.py --use-real --send
```

## Dateistruktur (wichtig)
- data/input/ — Tickerlisten & Caches (`ticker_name_map.pkl`, `all_tickers.csv`)
- data/output/pickle/ — Crawl‑Pickles (z. B. `251030-000011_crawler-ergebnis.pkl`)
- data/output/summaries/ — generierte Zusammenfassungen (.md)
- data/state/ — persistenter Alert‑State (z. B. `alerts.json`)
- src/ — Quellcode (crawler, summarizer, discord utils, scripts)

## Discord‑Alarm‑Format
Kompakte Alert‑Nachricht enthält:
- Kopf (⚠️ WSB‑ALARM) + Pickle‑Name (💾 ...)
- Zeitstempel
- Top‑Ticker (bis 3) mit Nennungen, Δ, Kurszeile (inkl. Pre/After‑Market), Trends (1h/24h/7d), Yahoo‑Link
- Kurz‑Summary + bis zu 3 News‑Headlines (Titel | Quelle | URL)

Ziel: schnelle visuelle Erkennung von plötzlichen Nennungs‑/Trend‑Anstiegen.

## Testen von News‑Fetch
Beispiel: NewsAPI‑Abruf prüfen:
```bash
python - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()/'src'))
from summarize_ticker import get_yf_news
import json
print(json.dumps(get_yf_news("BYND"), ensure_ascii=False, indent=2))
PY
```

## Alert‑Logik (Kurz)
Empfohlene, konfigurierte Schwellen (ENV):
- ALERT_MIN_ABS, ALERT_MIN_DELTA, ALERT_RATIO, ALERT_MIN_PRICE_MOVE, ALERT_MAX_PER_RUN, ALERT_COOLDOWN_H  
Vorschlag: Score‑basierter Filter + per‑Ticker Cooldown; Ergebnisse persistent in `data/state/alerts.json`.

## Weiteres / Anpassungen
- `src/scripts/test_discord_message.py` erzeugt eine Vorschau‑Nachricht; mit `--use-real` nutzt es die letzte Crawl‑Pickle.
- `src/summarize_ticker.py` erzeugt strukturierte Summaries: `{"summary": "...", "news": [...]}`.
- Änderbare Parameter via ENV (ALERT_*, NEWSAPI_*).

## Troubleshooting
- Keine News angezeigt:
  - Prüfe `NEWSAPI_KEY` in `config/.env` und Rate‑Limits von NewsAPI.
  - Stelle `NEWSAPI_WINDOW_HOURS` ggf. auf ein größeres Fenster.
- yfinance Errors (z. B. ungültige period):
  - Achte auf gültige `period`/`interval`-Kombinationen (`1d`, `5d`, `1mo`, ...).
- Falsche/alte Version importiert:
```bash
find . -name "__pycache__" -exec rm -rf {} +
python - <<'PY'
import inspect, sys
sys.path.insert(0, "src")
import discord_utils
print(discord_utils.__file__)
PY
```
- Logs prüfen:
  - `logs/` (falls vorhanden) oder stdout der service/cron Unit.
- Alerts werden zu häufig gesendet:
  - Erhöhe `ALERT_COOLDOWN_H`, `ALERT_MIN_ABS`, `ALERT_MIN_DELTA` oder senke `ALERT_MAX_PER_RUN`.

## Lizenz
MIT — passe bei Bedarf an.
