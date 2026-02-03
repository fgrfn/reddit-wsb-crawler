"""Health check script for Docker container monitoring.

Prüft ob der Crawler ordnungsgemäß funktioniert durch:
1. Überprüfung der letzten Log-Einträge
2. Zeitstempel des letzten erfolgreichen Crawls
3. Existenz wichtiger Dateien
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Pfade
BASE_DIR = Path("/app")
LOG_PATH = BASE_DIR / "logs" / "crawler.log"
HEARTBEAT_STATE = BASE_DIR / "data" / "state" / "heartbeat_state.json"

def check_health() -> bool:
    """Führt Health-Check durch.
    
    Returns:
        True wenn gesund, False sonst
    """
    try:
        # 1. Prüfe ob Log-Datei existiert und schreibbar ist
        if not LOG_PATH.exists():
            print("❌ Log-Datei nicht gefunden", file=sys.stderr)
            return False
        
        # 2. Prüfe letzten Log-Eintrag (max 2 Stunden alt)
        try:
            mtime = LOG_PATH.stat().st_mtime
            last_modified = datetime.fromtimestamp(mtime)
            age = datetime.now() - last_modified
            
            if age > timedelta(hours=2):
                print(f"❌ Log-Datei zu alt: {age.total_seconds()/3600:.1f}h", file=sys.stderr)
                return False
        except Exception as e:
            print(f"⚠️ Warnung beim Log-Check: {e}", file=sys.stderr)
            # Nicht kritisch, weitermachen
        
        # 3. Prüfe Heartbeat-State (wenn vorhanden)
        if HEARTBEAT_STATE.exists():
            try:
                import json
                with open(HEARTBEAT_STATE, 'r') as f:
                    state = json.load(f)
                last_update = state.get("last_update", "")
                
                # Parse Timestamp (Format: "dd.mm.yyyy HH:MM:SS")
                if last_update:
                    dt = datetime.strptime(last_update, "%d.%m.%Y %H:%M:%S")
                    age = datetime.now() - dt
                    
                    # Heartbeat sollte max 2 Stunden alt sein
                    if age > timedelta(hours=2):
                        print(f"⚠️ Heartbeat zu alt: {age.total_seconds()/3600:.1f}h", file=sys.stderr)
                        # Nicht kritisch für Health-Check
            except Exception as e:
                print(f"⚠️ Warnung beim Heartbeat-Check: {e}", file=sys.stderr)
        
        # 4. Prüfe ob wichtige Verzeichnisse existieren
        required_dirs = [
            BASE_DIR / "data" / "input",
            BASE_DIR / "data" / "output" / "pickle",
            BASE_DIR / "logs"
        ]
        
        for dir_path in required_dirs:
            if not dir_path.exists():
                print(f"❌ Verzeichnis fehlt: {dir_path}", file=sys.stderr)
                return False
        
        # Alles OK
        print("✅ Health-Check erfolgreich")
        return True
        
    except Exception as e:
        print(f"❌ Health-Check Fehler: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    is_healthy = check_health()
    sys.exit(0 if is_healthy else 1)
