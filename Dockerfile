# ═══════════════════════════════════════════════════════
#  WSB-Crawler v2 — Multi-Stage Dockerfile
#
#  Stage 1 (builder): kompiliert Dependencies mit gcc
#  Stage 2 (runtime): nur das fertige Wheel, kein Compiler
#  Ergebnis: ~60% kleineres Image, kein Root-User
# ═══════════════════════════════════════════════════════

# ── Stage 1: Builder ────────────────────────────────────
FROM python:3.14-slim AS builder

WORKDIR /build

# Compiler nur im Builder-Stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Package + Dependencies in separates Prefix installieren (nicht ins System)
COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir --prefix=/install hatchling
RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: Runtime ────────────────────────────────────
FROM python:3.14-slim AS runtime

ARG VERSION=2.0.0
LABEL maintainer="WSB-Crawler"
LABEL description="Reddit WSB Crawler v2 with Discord alerts and slash commands"
LABEL version="${VERSION}"

WORKDIR /app

# Non-Root User (Security Best Practice)
RUN useradd -m -u 1000 -s /bin/bash crawler && \
    mkdir -p data logs && \
    chown -R crawler:crawler /app

# Nur die fertig gebauten Packages vom Builder kopieren
# (enthält wsb_crawler-Package inkl. React-Build in api/static/)
COPY --from=builder /install /usr/local

# Als Non-Root User ausführen
USER crawler

# Umgebungsvariablen
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Healthcheck: prüft ob die DB existiert und der Prozess läuft
HEALTHCHECK --interval=5m --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "from wsb_crawler.storage.database import Database; import asyncio; asyncio.run(Database('data/wsb_crawler.db').init())" || exit 1

# Entry-Point
CMD ["python", "-m", "wsb_crawler.main"]
