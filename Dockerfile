# Dockerfile
FROM python:3.11-slim

# Arbeitsverzeichnis setzen
WORKDIR /app

# Projektdateien kopieren
COPY . /app

# Abhängigkeiten installieren
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Port für Streamlit
EXPOSE 8501

# Standard-Entrypoint: Streamlit starten
CMD ["streamlit", "run", "src/web_app.py", "--server.port=8501", "--server.headless=true"]