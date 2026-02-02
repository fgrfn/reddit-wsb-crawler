# Docker ohne .env Datei - Nur mit Environment-Variablen

Du kannst den WSB-Crawler auch **ohne** `config/.env` Datei starten, indem du alle Variablen direkt übergibst.

## Option 1: docker run

```bash
docker run -d \
  --name wsb-crawler \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -e REDDIT_CLIENT_ID="your_client_id" \
  -e REDDIT_CLIENT_SECRET="your_secret" \
  -e REDDIT_USER_AGENT="python:wsb-crawler:v1.0.0 (by /u/youruser)" \
  -e NEWSAPI_KEY="your_newsapi_key" \
  -e DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK" \
  -e SUBREDDITS="wallstreetbets,wallstreetbetsGER" \
  -e NEWSAPI_LANG="en" \
  -e NEWSAPI_WINDOW_HOURS="48" \
  -e DISCORD_STATUS_UPDATE="true" \
  -e ALERT_MIN_ABS="20" \
  -e ALERT_MIN_DELTA="10" \
  -e ALERT_RATIO="2.0" \
  -e ALERT_MIN_PRICE_MOVE="5.0" \
  -e ALERT_MAX_PER_RUN="3" \
  -e ALERT_COOLDOWN_H="4" \
  ghcr.io/fgrfn/reddit-wsb-crawler:latest
```

## Option 2: docker-compose mit Environment-Variablen

Setze die Variablen im Terminal oder in einer `.env` im **gleichen Verzeichnis** wie `docker-compose.yml`:

```bash
# Pflicht-Variablen setzen
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_secret"
export REDDIT_USER_AGENT="python:wsb-crawler:v1.0.0 (by /u/youruser)"
export NEWSAPI_KEY="your_newsapi_key"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK"

# Optional: Weitere Variablen setzen
export SUBREDDITS="wallstreetbets,mauerstrassenwetten"
export ALERT_MIN_ABS="30"
export CRAWL_INTERVAL="1800"  # 30 Minuten

# Starten (liest Variablen aus Shell Environment)
docker-compose up -d
```

## Option 3: Inline mit docker-compose

```bash
REDDIT_CLIENT_ID="xxx" \
REDDIT_CLIENT_SECRET="yyy" \
REDDIT_USER_AGENT="python:wsb-crawler:v1.0.0 (by /u/youruser)" \
NEWSAPI_KEY="zzz" \
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK" \
docker-compose up
```

## Option 4: Separate .env Datei (außerhalb config/)

Erstelle eine `.env` im Root-Verzeichnis (neben `docker-compose.yml`):

```bash
# .env (im Root, nicht in config/)
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_secret
REDDIT_USER_AGENT=python:wsb-crawler:v1.0.0 (by /u/youruser)
NEWSAPI_KEY=your_newsapi_key
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK

# Optional
SUBREDDITS=wallstreetbets,wallstreetbetsGER
ALERT_MIN_ABS=20
CRAWL_INTERVAL=3600
```

Docker Compose lädt diese automatisch!

## Priorität der Variablen

1. **Inline** (-e Flags / export im Terminal) - Höchste Priorität
2. **Shell Environment** (export VARIABLE=value)
3. **`.env` im Root** (neben docker-compose.yml)
4. **`config/.env`** (via env_file)
5. **Defaults** im docker-compose.yml (${VAR:-default})

## Pflicht-Variablen

Diese **müssen** gesetzt sein:
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`
- `NEWSAPI_KEY`
- `DISCORD_WEBHOOK_URL`

Alle anderen haben Defaults und sind optional!

## Kubernetes / Cloud Deployment

Für Cloud-Deployments kannst du Secrets verwenden:

```yaml
# kubernetes-deployment.yaml (Beispiel)
apiVersion: v1
kind: Secret
metadata:
  name: wsb-crawler-secrets
type: Opaque
stringData:
  REDDIT_CLIENT_ID: "your_client_id"
  REDDIT_CLIENT_SECRET: "your_secret"
  NEWSAPI_KEY: "your_key"
  DISCORD_WEBHOOK_URL: "your_webhook"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wsb-crawler
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: wsb-crawler
        image: ghcr.io/fgrfn/reddit-wsb-crawler:latest
        envFrom:
        - secretRef:
            name: wsb-crawler-secrets
        env:
        - name: SUBREDDITS
          value: "wallstreetbets,wallstreetbetsGER"
        - name: ALERT_MIN_ABS
          value: "20"
```

## Vorteile dieser Methode

✅ Keine `config/.env` Datei nötig
✅ Flexibler für CI/CD Pipelines
✅ Besser für Container-Orchestrierung (Kubernetes, Docker Swarm)
✅ Secrets Management über externe Tools möglich
✅ Einfaches Überschreiben einzelner Werte
