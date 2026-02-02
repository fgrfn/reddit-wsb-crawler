"""Resolver-Script: Löst Ticker-Symbole aus neuesten Pickle-Dateien zu Unternehmensnamen auf.

Durchsucht das neueste Crawl-Ergebnis und versucht, unbekannte Ticker-Symbole
über verschiedene APIs (Yahoo Finance, Alpha Vantage) aufzulösen.
"""
import os
import pickle
import csv
import requests
import yfinance as yf
from pathlib import Path
from colorama import Fore, Style, init
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from ticker_utils import load_tickerlist
import logging

# 🟢 Farbkonsole aktivieren
init(autoreset=True)

# 📁 Pfade
CSV_EXPORT_PATH = Path("data/output/latest_resolved_names.csv")
PKL_CACHE_PATH = Path("data/input/ticker_name_map.pkl")
CSV_CACHE_PATH = Path("data/input/ticker_name_map.csv")
PICKLE_DIR = Path("data/output/pickle")

# Logger einrichten
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

IGNORED_KEYS = {"relevant", "run_id", "subreddits", "total_posts"}

def resolve_symbol_parallel(symbol: str) -> tuple[str, str | None, str | None]:
    """Löst Ticker-Symbol parallel über Yahoo und Alpha Vantage auf.
    
    Args:
        symbol: Ticker-Symbol
    
    Returns:
        tuple: (symbol, company_name, provider) - provider ist "Yahoo", "Alpha" oder None
    """
    def from_yahoo():
        try:
            info = yf.Ticker(symbol).info
            name = info.get("longName") or info.get("shortName")
            if name and name != symbol:
                return "Yahoo", name
        except Exception:
            pass
        return None

    def from_alpha():
        key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if not key:
            return None
        try:
            url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={key}"
            r = requests.get(url, timeout=5)
            if r.ok:
                data = r.json()
                name = data.get("Name")
                if name:
                    return "Alpha", name
        except Exception:
            pass
        return None

    with ThreadPoolExecutor() as ex:
        f_y = ex.submit(from_yahoo)
        f_a = ex.submit(from_alpha)
        done = []
        for f in as_completed([f_y, f_a]):
            result = f.result()
            if result:
                provider, name = result
                return symbol, name, provider
            done.append(f)
        return symbol, None, None

def load_ticker_name_map() -> dict:
    """Lädt Ticker-Namen-Mapping aus Pickle-Cache."""
    if PKL_CACHE_PATH.exists():
        with open(PKL_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    return {}

def save_ticker_name_map(name_map: dict) -> None:
    """Speichert Ticker-Namen-Mapping als Pickle und CSV."""
    PKL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PKL_CACHE_PATH, "wb") as f:
        pickle.dump(name_map, f)
    with open(CSV_CACHE_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Ticker", "Company"])
        for sym, name in sorted(name_map.items()):
            writer.writerow([sym, name])

def resolve_from_latest_pickle():
    try:
        load_dotenv()

        # Neueste Pickle-Datei suchen
        pickle_files = sorted(PICKLE_DIR.glob("*.pkl"), reverse=True)
        if not pickle_files:
            print("❌ Keine Pickle-Datei gefunden.")
            logger.error("❌ Keine Pickle-Datei gefunden.")
            return
        latest_pickle = pickle_files[0]
        print(f"\n📜 Lese Treffer aus: {latest_pickle}")

        with open(latest_pickle, "rb") as f:
            try:
                counter = pickle.load(f)
            except Exception as e:
                print(f"{Fore.RED}❌ Fehler beim Lesen: {e}")
                logger.error(f"❌ Fehler beim Lesen der Pickle-Datei: {e}")
                raise

        if not counter:
            print(f"{Fore.YELLOW}⚪️ Keine Ticker in der Pickle-Datei.")
            logger.warning("⚪️ Keine Ticker in der Pickle-Datei.")
            return

        print(f"{Fore.LIGHTBLACK_EX}📊 Gesamt-Nennungen: {sum(v for v in counter.values() if isinstance(v, int))}")
        print(f"{Fore.LIGHTBLACK_EX}🔍 Einzigartige Ticker: {len(counter)}")

        name_map = load_ticker_name_map()
        print(f"{Fore.LIGHTBLACK_EX}📦 Ticker im Cache: {len(name_map)}")

        uncached = sorted(s for s in counter if s not in name_map and s not in IGNORED_KEYS)
        print(f"{Fore.YELLOW}🆕 Neue Ticker zur Auflösung: {len(uncached)}\n")

        # Zeige an, welche Ticker aus dem Cache kommen
        if name_map:
            for sym in sorted(counter):
                if sym in name_map:
                    print(f"{Fore.LIGHTGREEN_EX}🗃️ {sym:<6}{Style.RESET_ALL} → {name_map[sym]} (aus Cache)")

        if not uncached:
            print(f"{Fore.GREEN}✅ Alle Ticker bereits bekannt – nichts zu tun.")
            logger.info("✅ Alle Ticker bereits bekannt.")
            return

        # Versuche lokale Ticker-Liste
        tickers = load_tickerlist()
        symbol_to_name = dict(zip(tickers["Symbol"], tickers["Security Name"]))

        resolved = {}
        fallback_needed = []
        for sym in uncached:
            name = symbol_to_name.get(sym)
            if name:
                print(f"{Fore.GREEN}✅ {Fore.CYAN}{sym:<6}{Style.RESET_ALL} → {name} (lokale Liste)")
                logger.info(f"✅ {sym} → {name} (lokale Liste)")
                resolved[sym] = name
            else:
                print(f"{Fore.YELLOW}⚠️ {sym:<6} nicht in lokaler Liste, versuche Fallback (API)...")
                logger.warning(f"⚠️ {sym} nicht in lokaler Liste, versuche Fallback (API)...")
                fallback_needed.append(sym)

        # Fallback: API (parallel)
        if fallback_needed:
            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = {pool.submit(resolve_symbol_parallel, s): s for s in fallback_needed}
                for future in as_completed(futures):
                    sym, name, src = future.result()
                    if name:
                        print(f"{Fore.GREEN}✅ {Fore.CYAN}{sym:<6}{Style.RESET_ALL} → {name} ({src} Fallback)")
                        logger.info(f"✅ {sym} → {name} ({src} Fallback)")
                        resolved[sym] = name
                    else:
                        print(f"{Fore.LIGHTBLACK_EX}🕳️ {sym:<6} konnte nicht aufgelöst werden")
                        logger.error(f"❌ {sym} konnte nicht aufgelöst werden")

        if resolved:
            name_map.update(resolved)
            save_ticker_name_map(name_map)
            print(f"\n{Fore.GREEN}💾 Cache aktualisiert mit {len(resolved)} neuen Einträgen.")
            logger.info(f"💾 Cache aktualisiert mit {len(resolved)} neuen Einträgen.")

            CSV_EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CSV_EXPORT_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Ticker", "Company"])
                for sym in sorted(resolved):
                    writer.writerow([sym, resolved[sym]])
            print(f"{Fore.BLUE}📎 Exportiert nach: {CSV_EXPORT_PATH}")
        else:
            print(f"\n{Fore.YELLOW}⚠️ Keine neuen Namen auflösbar.")
            logger.warning("⚠️ Keine neuen Namen auflösbar.")

        logger.info("✅ Namensauflösung erfolgreich abgeschlossen.")

    except Exception as e:
        logger.error(f"❌ Fehler bei der Namensauflösung: {e}", exc_info=True)
        print(f"{Fore.RED}❌ Fehler bei der Namensauflösung: {e}")
        raise

if __name__ == "__main__":
    print("Resolver läuft!")
    logger.info(f"Starte resolve_latest_hits.py (cwd={os.getcwd()})")
    resolve_from_latest_pickle()
