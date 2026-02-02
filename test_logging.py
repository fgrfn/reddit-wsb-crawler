#!/usr/bin/env python3
"""Test-Script für Logging-Funktionalität in Docker."""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
BASE_DIR = Path(__file__).parent
LOG_PATH = BASE_DIR / "logs" / "test.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

print(f"🧪 Test-Script gestartet: {datetime.now()}")
print(f"📂 BASE_DIR: {BASE_DIR}")
print(f"📝 LOG_PATH: {LOG_PATH}")
print(f"🔍 Log-Verzeichnis existiert: {LOG_PATH.parent.exists()}")
print(f"✍️  Schreibrechte: {LOG_PATH.parent.stat().st_mode if LOG_PATH.parent.exists() else 'N/A'}")

# Custom handler with flush
class FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

# Setup handlers
file_handler = FlushFileHandler(LOG_PATH, encoding="utf-8")
file_handler.setLevel(logging.INFO)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[file_handler, stream_handler],
    force=True
)

logger = logging.getLogger(__name__)

# Test messages
logger.info("=" * 50)
logger.info("🧪 LOGGING TEST GESTARTET")
logger.info("=" * 50)
logger.info(f"📅 Zeitstempel: {datetime.now()}")
logger.info(f"🐍 Python Version: {sys.version}")
logger.info(f"📂 Working Directory: {Path.cwd()}")
logger.info(f"📝 Log-Datei: {LOG_PATH}")

# Test write permissions
try:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"# Manual write test: {datetime.now()}\n")
        f.flush()
    logger.info("✅ Manueller Schreibtest erfolgreich")
except Exception as e:
    logger.error(f"❌ Fehler beim manuellen Schreiben: {e}")

# Test multiple log levels
logger.debug("DEBUG: Diese Nachricht sollte nicht erscheinen (Level zu niedrig)")
logger.info("INFO: Standard-Log-Level")
logger.warning("WARNING: Testwarnung")
logger.error("ERROR: Testfehler (kein echter Fehler)")

# Test file size
if LOG_PATH.exists():
    size = LOG_PATH.stat().st_size
    logger.info(f"📊 Log-Datei Größe: {size} Bytes")
    if size == 0:
        logger.error("❌ LOG-DATEI IST LEER!")
    else:
        logger.info("✅ LOG-DATEI ENTHÄLT DATEN")
else:
    logger.error("❌ LOG-DATEI EXISTIERT NICHT!")

logger.info("=" * 50)
logger.info("✅ LOGGING TEST ABGESCHLOSSEN")
logger.info("=" * 50)

print("\n" + "=" * 50)
print("📋 ZUSAMMENFASSUNG:")
print("=" * 50)
if LOG_PATH.exists():
    print(f"✅ Log-Datei erstellt: {LOG_PATH}")
    print(f"📊 Größe: {LOG_PATH.stat().st_size} Bytes")
    print(f"\n📄 Inhalt der ersten 10 Zeilen:")
    print("-" * 50)
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if i > 10:
                break
            print(line.rstrip())
else:
    print(f"❌ Log-Datei nicht gefunden: {LOG_PATH}")

print("=" * 50)
