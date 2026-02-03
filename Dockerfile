# WSB-Crawler Dockerfile
FROM python:3.11-slim

# Metadaten
LABEL maintainer="WSB-Crawler"
LABEL description="Reddit WSB Crawler with Discord alerts"
LABEL version="1.5.10"

# Arbeitsverzeichnis erstellen
WORKDIR /app

# System-Dependencies installieren
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Python-Dependencies installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application-Code kopieren
COPY src/ ./src/
COPY config/ ./config/

# Verzeichnisse für Daten erstellen
RUN mkdir -p \
    data/input \
    data/output/pickle \
    data/output/summaries \
    data/state \
    logs \
    logs/archive

# Version anzeigen
COPY src/__version__.py ./src/
RUN python -c "from src.__version__ import __version__; print(f'Building WSB-Crawler v{__version__}')"

# Umgebungsvariablen
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Healthcheck
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s --retries=3 \
    CMD python src/health_check.py

# Standard-Command: Headless-Crawler ausführen
CMD ["python", "src/run_crawler_headless.py"]
