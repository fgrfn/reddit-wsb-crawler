import os
import pickle
import csv
import logging
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv
from colorama import Fore, Style, init
from concurrent.futures import ThreadPoolExecutor, as_completed
from resolver_utils import resolve_symbol_parallel

# 🟢 Farbunterstützung
init(autoreset=True)
load_dotenv()

# 🔧 Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 📁 Pfade
SYMBOLS_PATH = Path("data/input/symbols_list.pkl")
CACHE_PATH = Path("data/input/ticker_name_map.pkl")
CSV_PATH = Path("data/input/ticker_name_map.csv")

def load_cache():
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(cache, f)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Ticker", "Company"])
        for sym, name in sorted(cache.items()):
            writer.writerow([sym, name])

def main():
    if not SYMBOLS_PATH.exists():
        logger.warning(f"{Fore.RED}⚠️ symbols_list.pkl fehlt unter: {SYMBOLS_PATH}")
        return

    with open(SYMBOLS_PATH, "rb") as f:
        symbols = set(pickle.load(f))

    logger.info(f"🔍 {len(symbols)} Ticker geladen")

    cache = load_cache()
    known = set(cache)
    to_resolve = sorted(symbols - known)

    logger.info(f"📦 {len(known)} Ticker im Cache")
    logger.info(f"🆕 {len(to_resolve)} neue Ticker werden aufgelöst\n")

    resolved = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(resolve_symbol_parallel, s): s for s in to_resolve}
        for future in tqdm(as_completed(futures), total=len(to_resolve), desc="🔎 Auflösung", ncols=80):
            sym, name, provider = future.result()
            if name:
                print(f"{Fore.GREEN}✅ {sym:<6}{Style.RESET_ALL} → {name} {Fore.LIGHTBLACK_EX}[{provider}]")
                resolved[sym] = name
            else:
                print(f"{Fore.LIGHTBLACK_EX}🕳️ {sym:<6} konnte nicht aufgelöst werden")

    if resolved:
        cache.update(resolved)
        save_cache(cache)
        print(f"\n{Fore.GREEN}💾 Cache aktualisiert mit {len(resolved)} neuen Namen.")
        print(f"{Fore.BLUE}📎 Exportiert nach: {CSV_PATH}")
    else:
        print(f"\n{Fore.YELLOW}⚪️ Keine neuen Namen auflösbar.")

if __name__ == "__main__":
    main()
