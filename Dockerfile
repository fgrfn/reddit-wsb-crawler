# ═══════════════════════════════════════════════════════
#  WSB-Crawler v2 — Multi-Stage Dockerfile
#
#  Stage 1 (builder): kompiliert Dependencies mit gcc
#  Stage 2 (runtime): nur das fertige Wheel, kein Compiler
#  Ergebnis: ~60% kleineres Image, Non-Root-App-Prozess
# ═══════════════════════════════════════════════════════

# ── Stage 1: Builder ────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Compiler nur im Builder-Stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Package + Dependencies in separates Prefix installieren (nicht ins System)
# README.md wird mitkopiert, weil pyproject.toml es als `readme` deklariert —
# hatchling bricht sonst beim Metadaten-Bauen ab.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --prefix=/install hatchling
RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: Runtime ────────────────────────────────────
FROM python:3.13-slim AS runtime

ARG VERSION=2.0.0
LABEL maintainer="WSB-Crawler"
LABEL description="Reddit WSB Crawler v2 with Discord alerts and slash commands"
LABEL version="${VERSION}"

WORKDIR /app

# gosu wird nur im EntryPoint genutzt, um nach dem Fixen der bind-mounted
# data/logs-Verzeichnisse auf den Non-Root-User zu wechseln.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Non-Root User (Security Best Practice). Der EntryPoint passt UID/GID bei
# Bedarf per PUID/PGID an und korrigiert die Rechte von /app/data und /app/logs.
RUN useradd -m -u 1000 -s /bin/bash crawler && \
    mkdir -p data logs && \
    chown -R crawler:crawler /app

# Nur die fertig gebauten Packages vom Builder kopieren
# (enthält wsb_crawler-Package inkl. HTML-Dashboard in api/static/)
COPY --from=builder /install /usr/local
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Umgebungsvariablen
# WSB_HOST=0.0.0.0 ist im Container nötig, damit das Port-Mapping funktioniert
# (der App-Default ist aus Sicherheitsgründen 127.0.0.1)
ENV PYTHONUNBUFFERED=1 \
    WSB_HOST=0.0.0.0 \
    WSB_NO_BROWSER=1 \
    WSB_DB_PATH=/app/data/wsb_crawler.db \
    PUID=1000 \
    PGID=1000

# Healthcheck: API antwortet? (Der frühere DB-Check übergab einen str statt
# Path an Database() und schlug damit immer fehl.)
HEALTHCHECK --interval=5m --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"WSB_PORT\", \"80\")}/api/status', timeout=5)" || exit 1

# EntryPoint läuft kurz als root, setzt Rechte auf bind-mounted Volumes und
# startet die App danach via gosu als crawler.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "-m", "wsb_crawler.main"]
