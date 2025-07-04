import os
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
import zipfile

def archive_log(log_path: Path, archive_dir: Path, zip_old_logs: bool = False, keep_last: int = None):
    if not log_path.exists():
        print("⚠️ Kein Logfile zum Archivieren.")
        return

    archive_dir.mkdir(parents=True, exist_ok=True)

    # 🗓️ Zeitstempel für eindeutigen Namen
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = log_path.stem
    archive_file = archive_dir / f"{base_name}_{timestamp}.log"

    # 🧠 Deduplizieren: Falls identischer Hash schon im Archiv, abbrechen
    with open(log_path, "rb") as f:
        log_data = f.read()
        current_hash = hashlib.sha256(log_data).hexdigest()

    for existing_log in archive_dir.glob(f"{base_name}_*.log"):
        with open(existing_log, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() == current_hash:
                print("⚠️ Identisches Logfile existiert bereits im Archiv. Kein Duplikat gespeichert.")
                return

    shutil.move(str(log_path), str(archive_file))
    print(f"✅ Logfile archiviert unter: {archive_file}")

    # 🎁 Optional: Alte Logs zippen, um Platz zu sparen
    if zip_old_logs:
        for old_log in archive_dir.glob(f"{base_name}_*.log"):
            zip_path = old_log.with_suffix(".zip")
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(old_log, arcname=old_log.name)
            old_log.unlink()
            print(f"📦 Archiv komprimiert: {zip_path.name}")

    # 🧹 Ältere Logs löschen, wenn Limit gesetzt ist
    if keep_last is not None:
        archived_logs = sorted(
            archive_dir.glob(f"{base_name}_*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        for old_file in archived_logs[keep_last:]:
            old_file.unlink()
            print(f"🧹 Alte Log-Datei gelöscht: {old_file.name}")
