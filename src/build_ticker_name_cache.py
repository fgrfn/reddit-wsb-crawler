"""Cache-Builder: Löst alle Ticker aus symbols_list.pkl zu Unternehmensnamen auf.

Durchläuft alle bekannten Ticker-Symbole und erstellt/erweitert einen
persistenten Cache mit Unternehmensnamen von Yahoo Finance.
"""
import os
import pickle
import csv
import logging
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv
from colorama import Fore, Style, init
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# 🟢 Farbunterstützung
init(autoreset=True)
load_dotenv()

# 🔧 Logging - stdout für saubere Subprozess-Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# 📁 Pfade
SYMBOLS_PATH = Path("data/input/symbols_list.pkl")
CACHE_PATH = Path("data/input/ticker_name_map.pkl")
CSV_PATH = Path("data/input/ticker_name_map.csv")

def load_cache() -> dict:
    """Lädt den Ticker-Namen-Cache."""
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)
    return {}

def save_cache(cache: dict) -> None:
    """Speichert den Cache als Pickle und CSV."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(cache, f)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Ticker", "Company"])
        for sym, name in sorted(cache.items()):
            writer.writerow([sym, name])

def resolve_symbol_parallel(symbol: str) -> tuple[str, str | None, str]:
    """Löst Symbol parallel über Yahoo Finance und Yahoo API.
    
    Returns:
        tuple: (symbol, company_name, provider)
    """
    import yfinance as yf
    import requests
    # 1. yfinance
    try:
        info = yf.Ticker(symbol).info
        name = info.get("longName") or info.get("shortName")
        if name and name != symbol:
            return symbol, name, "yfinance"
    except Exception:
        pass
    # 2. Yahoo API
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}"
        response = requests.get(url, headers=headers, timeout=5)
        if response.ok:
            data = response.json()
            for result in data.get("quotes", []):
                if result.get("symbol") == symbol and result.get("shortname"):
                    return symbol, result["shortname"], "YahooAPI"
    except Exception:
        pass
    return symbol, None, "None"

def main():
    if not SYMBOLS_PATH.exists():
        logger.warning(f"{Fore.RED}⚠️ symbols_list.pkl fehlt unter: {SYMBOLS_PATH}")
        sys.exit(1)  # Fehlercode zurückgeben

    with open(SYMBOLS_PATH, "rb") as f:
        symbols = set(pickle.load(f))
    # Nur Strings zulassen!
    symbols = set(s for s in symbols if isinstance(s, str) and s.isalpha())

    logger.info(f"🔍 {len(symbols)} Ticker geladen")

    cache = load_cache()
    known = set(cache)
    to_resolve = sorted(symbols - known)

    logger.info(f"📦 {len(known)} Ticker im Cache")
    logger.info(f"🆕 {len(to_resolve)} neue Ticker werden aufgelöst\n")

    resolved = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(resolve_symbol_parallel, s): s for s in to_resolve}
        success_count = 0
        with tqdm(
            as_completed(futures),
            total=len(to_resolve),
            desc=f"🔎 Auflösung (0/{len(to_resolve)})",
            ncols=80
        ) as pbar:
            for future in pbar:
                try:
                    sym, name, provider = future.result()
                    if name:
                        logger.info(f"✅ {sym:<6} → {name} [{provider}]")
                        print(f"{Fore.GREEN}✅ {sym:<6}{Style.RESET_ALL} → {name} {Fore.LIGHTBLACK_EX}[{provider}]")
                        resolved[sym] = name
                        success_count += 1
                    else:
                        logger.warning(f"🕳️ {sym:<6} konnte nicht aufgelöst werden")
                        print(f"{Fore.LIGHTBLACK_EX}🕳️ {sym:<6} konnte nicht aufgelöst werden")
                except Exception as e:
                    sym = futures[future]
                    logger.error(f"❌ Fehler bei {sym}: {e}")
                    print(f"{Fore.RED}❌ Fehler bei {sym}: {e}")
                pbar.set_description(f"🔎 Auflösung ({success_count}/{len(to_resolve)})")

    if resolved:
        cache.update(resolved)
        save_cache(cache)
        print(f"\n{Fore.GREEN}💾 Cache aktualisiert mit {len(resolved)} neuen Namen.")
        print(f"{Fore.BLUE}📎 Exportiert nach: {CSV_PATH}")
        return len(resolved)
    else:
        print(f"\n{Fore.YELLOW}⚪️ Keine neuen Namen auflösbar.")
        return 0

if __name__ == "__main__":
    count = main()
    sys.exit(0 if count is not None else 1)
