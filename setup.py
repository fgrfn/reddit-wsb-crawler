#!/usr/bin/env python3
"""
WSB-Crawler Setup-Script
Installiert alle Abhängigkeiten, richtet den Autostart ein und startet den Crawler.

Unterstützte Plattformen:
  - Windows (Task Scheduler)
  - Linux (systemd User-Service)
  - macOS (launchd plist)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable
SYSTEM = platform.system()  # "Windows", "Linux", "Darwin"

RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def info(msg: str) -> None:
    print(f"{CYAN}  →{RESET} {msg}")


def ok(msg: str) -> None:
    print(f"{GREEN}  ✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}  ⚠{RESET} {msg}")


def error(msg: str) -> None:
    print(f"{RED}  ✗{RESET} {msg}")


def heading(msg: str) -> None:
    print(f"\n{BOLD}{msg}{RESET}")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


def check_python_version() -> None:
    heading("1. Python-Version prüfen")
    v = sys.version_info
    if v < (3, 11):
        error(f"Python 3.11+ erforderlich, gefunden: {v.major}.{v.minor}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def check_node() -> bool:
    heading("2. Node.js prüfen (für Frontend-Build)")
    if shutil.which("node") and shutil.which("npm"):
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        ok(f"Node.js {result.stdout.strip()}")
        return True
    warn("Node.js nicht gefunden — Frontend-Build wird übersprungen.")
    warn("Dashboard funktioniert trotzdem (nur ohne React-Build).")
    info("Node.js installieren unter: https://nodejs.org")
    return False


def install_python_deps() -> None:
    heading("3. Python-Abhängigkeiten installieren")
    info("pip install -e .")
    run([PYTHON, "-m", "pip", "install", "-e", str(REPO_DIR)], cwd=REPO_DIR)
    ok("Python-Pakete installiert")


def build_frontend(has_node: bool) -> None:
    heading("4. Frontend bauen")
    web_dir = REPO_DIR / "web"
    if not has_node:
        warn("Übersprungen (Node.js nicht verfügbar)")
        return
    if not web_dir.exists():
        warn("web/ Verzeichnis nicht gefunden — übersprungen")
        return

    info("npm install")
    run(["npm", "install"], cwd=web_dir)
    info("npm run build")
    run(["npm", "run", "build"], cwd=web_dir)
    ok("Frontend gebaut → src/wsb_crawler/api/static/")


def create_data_dirs() -> None:
    heading("5. Verzeichnisse anlegen")
    for d in ["data", "logs"]:
        (REPO_DIR / d).mkdir(exist_ok=True)
        ok(f"{d}/")


def setup_autostart() -> bool:
    heading("6. Autostart einrichten")
    print(f"  Soll WSB-Crawler beim {_start_event()} automatisch starten? [j/N] ", end="")
    answer = input().strip().lower()
    if answer not in ("j", "y", "ja", "yes"):
        info("Übersprungen")
        return False

    if SYSTEM == "Windows":
        return _autostart_windows()
    elif SYSTEM == "Linux":
        return _autostart_linux()
    elif SYSTEM == "Darwin":
        return _autostart_macos()
    else:
        warn(f"Autostart für {SYSTEM} nicht unterstützt")
        return False


def _start_event() -> str:
    if SYSTEM == "Windows":
        return "Windows-Anmeldung"
    elif SYSTEM == "Darwin":
        return "macOS-Login"
    return "System-Start"


def _autostart_windows() -> bool:
    """Windows Task Scheduler — startet bei Anmeldung, minimiert."""
    task_name = "WSB-Crawler"
    wsb_crawler_exe = shutil.which("wsb-crawler")
    if not wsb_crawler_exe:
        # Fallback: direkt via Python
        wsb_crawler_exe = str(REPO_DIR / "venv" / "Scripts" / "wsb-crawler.exe")

    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>WSB-Crawler Dashboard</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions>
    <Exec>
      <Command>{wsb_crawler_exe}</Command>
      <WorkingDirectory>{REPO_DIR}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

    xml_path = REPO_DIR / "wsb_crawler_task.xml"
    xml_path.write_text(xml, encoding="utf-16")

    try:
        run(
            ["schtasks", "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
            capture_output=True,
        )
        xml_path.unlink(missing_ok=True)
        ok(f"Windows Task '{task_name}' eingerichtet (startet bei Anmeldung)")
        return True
    except subprocess.CalledProcessError as e:
        error(f"Task konnte nicht erstellt werden: {e}")
        xml_path.unlink(missing_ok=True)
        return False


def _autostart_linux() -> bool:
    """systemd User-Service."""
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    service_file = service_dir / "wsb-crawler.service"

    wsb_crawler_bin = shutil.which("wsb-crawler") or f"{PYTHON} -m wsb_crawler.main"

    service = f"""[Unit]
Description=WSB-Crawler Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={REPO_DIR}
ExecStart={wsb_crawler_bin}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""
    service_file.write_text(service)

    try:
        run(["systemctl", "--user", "daemon-reload"])
        run(["systemctl", "--user", "enable", "--now", "wsb-crawler.service"])
        ok("systemd User-Service aktiviert (startet bei Login)")
        return True
    except subprocess.CalledProcessError as e:
        error(f"systemd-Fehler: {e}")
        warn(f"Service-Datei liegt unter: {service_file}")
        return False


def _autostart_macos() -> bool:
    """launchd plist."""
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_file = plist_dir / "com.wsb-crawler.plist"

    wsb_crawler_bin = shutil.which("wsb-crawler") or PYTHON

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.wsb-crawler</string>
    <key>ProgramArguments</key>
    <array>
        <string>{wsb_crawler_bin}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{REPO_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{REPO_DIR}/logs/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>{REPO_DIR}/logs/launchd.log</string>
</dict>
</plist>
"""
    plist_file.write_text(plist)

    try:
        run(["launchctl", "load", "-w", str(plist_file)])
        ok("launchd Agent geladen (startet bei Login)")
        return True
    except subprocess.CalledProcessError as e:
        error(f"launchctl-Fehler: {e}")
        warn(f"Plist liegt unter: {plist_file}")
        return False


def print_summary(autostart_ok: bool) -> None:
    heading("✓ Setup abgeschlossen!")
    print()
    print(f"  {BOLD}Crawler starten:{RESET}")
    print(f"    wsb-crawler")
    print()
    print(f"  {BOLD}Dashboard:{RESET}")
    print(f"    http://localhost:8080")
    print()
    if not autostart_ok:
        print(f"  {BOLD}Autostart (manuell):{RESET}")
        if SYSTEM == "Windows":
            print(f"    schtasks /Run /TN WSB-Crawler")
        elif SYSTEM == "Linux":
            print(f"    systemctl --user enable --now wsb-crawler.service")
        elif SYSTEM == "Darwin":
            print(f"    launchctl load ~/Library/LaunchAgents/com.wsb-crawler.plist")
        print()

    print(f"  {YELLOW}Beim ersten Start öffnet sich der Setup-Wizard im Browser.{RESET}")
    print()


def main() -> None:
    print(f"\n{BOLD}WSB-Crawler — Setup{RESET}\n")

    check_python_version()
    has_node = check_node()
    install_python_deps()
    build_frontend(has_node)
    create_data_dirs()
    autostart_ok = setup_autostart()
    print_summary(autostart_ok)

    print("Jetzt starten? [J/n] ", end="")
    if input().strip().lower() not in ("n", "nein", "no"):
        info("wsb-crawler startet…")
        os.execv(
            sys.executable,
            [sys.executable, "-m", "wsb_crawler.main"],
        )


if __name__ == "__main__":
    main()
