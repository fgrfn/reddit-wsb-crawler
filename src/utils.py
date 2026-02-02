"""Utility-Funktionen für Pickle-/Summary-Handling und .env-Verwaltung.

Diese Datei enthält Legacy-Funktionen, die auf ticker_data.py migriert wurden.
Für Tickerlist-Funktionen nutze ticker_utils.py.
"""
import os
import pickle
from pathlib import Path
import pandas as pd

TICKER_CSV = Path("data/input/all_tickers.csv")

def update_dotenv_variable(key: str, value: str, dotenv_path):
    from pathlib import Path
    import os
    dotenv_path = Path(dotenv_path)
    dotenv_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if dotenv_path.exists():
        with open(dotenv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    found = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(dotenv_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ[key] = value

def list_pickle_files(pickle_dir: Path):
    pickle_dir.mkdir(parents=True, exist_ok=True)
    return sorted([f.name for f in pickle_dir.glob("*.pkl")], reverse=True)

def list_summary_files(summary_dir: Path):
    summary_dir.mkdir(parents=True, exist_ok=True)
    return sorted([f.name for f in summary_dir.glob("*.md")], reverse=True)

def find_summary_for(pickle_file: str, summary_dir: Path):
    base = pickle_file.split("_")[0]
    for f in list_summary_files(summary_dir):
        if base in f:
            return summary_dir / f
    return None

def load_pickle(path: Path):
    with open(path, "rb") as f:
        return pickle.load(f)

def load_summary(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def parse_summary_md(text: str):
    blocks = text.strip().split("## ")
    summary_dict = {}
    for block in blocks[1:]:
        lines = block.split("\n", 1)
        if len(lines) == 2:
            summary_dict[lines[0].strip()] = lines[1].strip()
    return summary_dict

def load_ticker_names(ticker_name_path: Path):
    if ticker_name_path.exists():
        with open(ticker_name_path, "rb") as f:
            return pickle.load(f)
    return {}

def download_and_clean_tickerlist():
    """Legacy-Wrapper. Nutze stattdessen ticker_utils.download_and_clean_tickerlist()."""
    from ticker_utils import download_and_clean_tickerlist as _download
    return _download()

def load_tickerlist():
    """Lädt Tickerliste aus CSV oder lädt sie neu herunter."""
    if not TICKER_CSV.exists():
        return download_and_clean_tickerlist()
    return pd.read_csv(TICKER_CSV)

# Kompatibilitäts-Wrapper: importiere alle Hilfsfunktionen aus ticker_data
from ticker_data import *  # noqa: F401, F403
