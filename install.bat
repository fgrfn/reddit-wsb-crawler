@echo off
REM Installationsskript für reddit-wbs-crawler

echo Erstelle virtuelle Umgebung ...
python -m venv .venv

echo Aktiviere virtuelle Umgebung ...
call .venv\Scripts\activate

echo Installiere Python-Abhängigkeiten ...
pip install --upgrade pip
pip install -r requirements.txt

echo Erstelle benötigte Ordner ...
mkdir data\input
mkdir data\output
mkdir logs
mkdir logs\archive
mkdir config

echo Erstelle leere .env Datei (falls nicht vorhanden) ...
if not exist config\.env (
    echo # Beispiel-Umgebungsvariablen> config\.env
    echo OPENAI_API_KEY=>> config\.env
    echo REDDIT_CLIENT_ID=>> config\.env
    echo REDDIT_CLIENT_SECRET=>> config\.env
    echo REDDIT_USER_AGENT=>> config\.env
    echo SUBREDDITS=wallstreetbets>> config\.env
)

echo Installation abgeschlossen!
pause