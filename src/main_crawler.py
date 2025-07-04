import sys
import time
import logging
import subprocess
import os
import pickle
from pathlib import Path
from reddit_crawler import reddit_crawler
from log_utils import archive_log
from ticker_utils import SYMBOLS_PKL, download_and_clean_tickerlist

# 📁 Basisverzeichnis
BASE_DIR = Path(__file__).resolve().parent

# 📄 Pfade
LOG_PATH = BASE_DIR / "logs" / "crawler.log"
RESOLVER_LOG = BASE_DIR / "logs" / "resolver.log"
ARCHIVE_DIR = BASE_DIR / "logs" / "archive"
NAME_RESOLVER_SCRIPT = BASE_DIR / "resolve_latest_hits.py"
LATEST_HITS_FILE = BASE_DIR / "data" / "output" / "latest_ticker_hits.pkl"

# 🗂️ Verzeichnisse sicherstellen
for path in [LOG_PATH.parent, ARCHIVE_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# 🔧 Logging-Konfiguration
logfile = "logs/crawler.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(logfile, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def wait_for_file(path: Path, timeout=10):
    logger.info(f"⏳ Warte auf {path.name} (max {timeout}s) ...")
    if path.exists():  # <-- Diese Zeile ist wichtig!
        return True
    start = time.time()
    while time.time() - start < timeout:
        if path.exists():
            return True
        time.sleep(1)
    return False

def ensure_symbols_list(tickers):
    SYMBOLS_PKL.parent.mkdir(parents=True, exist_ok=True)
    with open(SYMBOLS_PKL, "wb") as f:
        pickle.dump(list(tickers["Symbol"]), f)
    logger.info(f"symbols_list.pkl wurde neu erstellt mit {len(tickers)} Symbolen.")

def main():
    tickers = download_and_clean_tickerlist()  # Listen immer neu laden und loggen
    ensure_symbols_list(tickers)
    start_time = time.time()
    logger.info("🕷️ Crawl gestartet")

    # Emoji direkt im String verwenden, nicht als Unicode-Escape!
    try:
        print("🕷️ Starte Reddit-Crawler ...")
    except UnicodeEncodeError:
        print("Starte Reddit-Crawler ...")

    try:
        reddit_crawler()
    except Exception:
        logger.exception("❌ Fehler beim Reddit-Crawl")
        return

    duration = round(time.time() - start_time, 2)
    logger.info(f"✅ Crawl abgeschlossen – Dauer: {duration} Sekunden")

    if not wait_for_file(LATEST_HITS_FILE, timeout=12):
        logger.error("⚠️ Timeout – keine neue Trefferdatei gefunden")
        return

    logger.info("📡 Starte Ticker-Namensauflösung ...")
    try:
        logger.info(f"Starte Resolver: {NAME_RESOLVER_SCRIPT} (cwd={os.getcwd()})")
        # Ausgabe in Konsole UND Logfile
        process = subprocess.Popen(
            [sys.executable, str(NAME_RESOLVER_SCRIPT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        with open(RESOLVER_LOG, "a", encoding="utf-8") as out:
            for line in process.stdout:
                print(line, end="")   # In die Konsole/WebUI
                out.write(line)       # In die Logdatei
        process.wait()
        logger.info("✅ Ticker-Namensauflösung abgeschlossen")
    except Exception:
        logger.exception("⚠️ Fehler bei der Namensauflösung")

    try:
        archive_log(LOG_PATH, ARCHIVE_DIR, keep_last=10)
        logger.info("📦 Log archiviert")
    except Exception as e:
        logger.warning(f"⚠️ Fehler beim Log-Rotate: {e}")

if __name__ == "__main__":
    main()
