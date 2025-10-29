# WSB-Crawler

Leichter Reddit-Crawler für r/wallstreetbets (inkl. DE-Subreddit).  
Sammelt Ticker‑Erwähnungen, identifiziert relevante Kandidaten, holt Kursdaten (yfinance) und Headlines (NewsAPI) und sendet kompakte Discord‑Alarme mit Kurs, Trends und News.

## Hauptfunktionen
- Zählt Ticker‑Erwähnungen in konfigurierbaren Subreddits
- Holt Kursdaten (yfinance) inkl. Pre/After‑Market und Trendkennzahlen (1h/24h/7d)
- Ruft Headlines ausschließlich über NewsAPI ab (NEWSAPI_KEY erforderlich)
- Erzeugt kurze lokale Zusammenfassungen und speichert sie
- Sendet kompakte Alarm‑Nachrichten an Discord (Webhook)

## Anforderungen
- Python 3.9+
- Abhängigkeiten: siehe `requirements.txt` (im Repo‑Root)
  ```bash
  pip install -r requirements.txt
  ```

## Konfiguration
Lege eine `.env` unter `config/.env` (repo‑root) an. Beispiel (ersetze Platzhalter mit echten Werten):

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

# Alarm thresholds
ALERT_RATIO=2.0
ALERT_MIN_DELTA=10
ALERT_MIN_ABS=20
```

Hinweis: `config/.env` im Repo‑Root wird bevorzugt. Es gibt Fallbacks (`src/config/.env`, `./config/.env`) falls nötig.

## Schnellstart / Befehle
- Voller Headless‑Crawl:
  ```bash
  python src/run_crawler_headless.py
  ```
- Lokale Discord‑Preview (nutzt neueste Pickle):
  ```bash
  python src/scripts/test_discord_message.py --use-real
  ```
- Preview + Senden (benötigt gültigen DISCORD_WEBHOOK_URL):
  ```bash
  python src/scripts/test_discord_message.py --use-real --send
  ```

## Dateistruktur (wichtig)
- data/input/ — Tickerlisten & Caches (z. B. `ticker_name_map.pkl`)
- data/output/pickle/ — Crawl‑Pickles (z. B. `251030-000011_crawler-ergebnis.pkl`)
- data/output/summaries/ — generierte Zusammenfassungen (.md)
- src/ — Quellcode (crawler, summarizer, discord utils, scripts)

## Testen von News‑Fetch
Führe diesen kurzen Test aus, um NewsAPI‑Ergebnisse zu sehen:
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

## Troubleshooting
- Keine News: überprüfe `NEWSAPI_KEY` und Rate‑Limits von NewsAPI.
- Fehlende/alte Codeversion: lösche `__pycache__` und starte Skripte neu.
  ```bash
  find . -name "__pycache__" -exec rm -rf {} +
  ```
- Welches Modul wird importiert:
  ```bash
  python - <<'PY'
  import inspect, sys
  sys.path.insert(0, "src")
  import discord_utils
  print(discord_utils.__file__)
  PY
  ```

## Weiteres / Anpassungen
- Alarm‑Schwellen sind per ENV veränderbar (ALERT_*).
- README kann erweitert (Deployment, systemd, CI). Ein `config/.env.example` kann bei Bedarf hinzugefügt werden.

## Lizenz
MIT — siehe LICENSE (falls vorhanden).
```// filepath: vscode-vfs://github/fgrfn/reddit-wsb-crawler/README.md
# WSB-Crawler

Leichter Reddit-Crawler für r/wallstreetbets (inkl. DE-Subreddit).  
Sammelt Ticker‑Erwähnungen, identifiziert relevante Kandidaten, holt Kursdaten (yfinance) und Headlines (NewsAPI) und sendet kompakte Discord‑Alarme mit Kurs, Trends und News.

## Hauptfunktionen
- Zählt Ticker‑Erwähnungen in konfigurierbaren Subreddits
- Holt Kursdaten (yfinance) inkl. Pre/After‑Market und Trendkennzahlen (1h/24h/7d)
- Ruft Headlines ausschließlich über NewsAPI ab (NEWSAPI_KEY erforderlich)
- Erzeugt kurze lokale Zusammenfassungen und speichert sie
- Sendet kompakte Alarm‑Nachrichten an Discord (Webhook)

## Anforderungen
- Python 3.9+
- Abhängigkeiten: siehe `requirements.txt` (im Repo‑Root)
  ```bash
  pip install -r requirements.txt
  ```

## Konfiguration
Lege eine `.env` unter `config/.env` (repo‑root) an. Beispiel (ersetze Platzhalter mit echten Werten):

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

# Alarm thresholds
ALERT_RATIO=2.0
ALERT_MIN_DELTA=10
ALERT_MIN_ABS=20
```

Hinweis: `config/.env` im Repo‑Root wird bevorzugt. Es gibt Fallbacks (`src/config/.env`, `./config/.env`) falls nötig.

## Schnellstart / Befehle
- Voller Headless‑Crawl:
  ```bash
  python src/run_crawler_headless.py
  ```
- Lokale Discord‑Preview (nutzt neueste Pickle):
  ```bash
  python src/scripts/test_discord_message.py --use-real
  ```
- Preview + Senden (benötigt gültigen DISCORD_WEBHOOK_URL):
  ```bash
  python src/scripts/test_discord_message.py --use-real --send
  ```

## Dateistruktur (wichtig)
- data/input/ — Tickerlisten & Caches (z. B. `ticker_name_map.pkl`)
- data/output/pickle/ — Crawl‑Pickles (z. B. `251030-000011_crawler-ergebnis.pkl`)
- data/output/summaries/ — generierte Zusammenfassungen (.md)
- src/ — Quellcode (crawler, summarizer, discord utils, scripts)

## Testen von News‑Fetch
Führe diesen kurzen Test aus, um NewsAPI‑Ergebnisse zu sehen:
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

## Troubleshooting
- Keine News: überprüfe `NEWSAPI_KEY` und Rate‑Limits von NewsAPI.
- Fehlende/alte Codeversion: lösche `__pycache__` und starte Skripte neu.
  ```bash
  find . -name "__pycache__" -exec rm -rf {} +
  ```
- Welches Modul wird importiert:
  ```bash
  python - <<'PY'
  import inspect, sys
  sys.path.insert(0, "src")
  import discord_utils
  print(discord_utils.__file__)
  PY
  ```

## Weiteres / Anpassungen
- Alarm‑Schwellen sind per ENV veränderbar (ALERT_*).
- README kann erweitert (Deployment, systemd, CI). Ein `config/.env.example` kann bei Bedarf hinzugefügt werden.

## Lizenz
MIT — siehe LICENSE (falls vorhanden).