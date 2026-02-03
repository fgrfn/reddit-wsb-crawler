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
            logger.error("❌ Keine Pickle-Datei gefunden.")
            return
        latest_pickle = pickle_files[0]
        logger.info(f"📜 Lese Treffer aus: {latest_pickle.name}")

        with open(latest_pickle, "rb") as f:
            try:
                counter = pickle.load(f)
            except Exception as e:
                logger.error(f"❌ Fehler beim Lesen der Pickle-Datei: {e}")
                raise

        if not counter:
            logger.warning("⚪️ Keine Ticker in der Pickle-Datei.")
            return

        total_mentions = sum(v for v in counter.values() if isinstance(v, int))
        logger.info(f"📊 Gesamt-Nennungen: {total_mentions}, 🔍 Einzigartige Ticker: {len(counter)}")

        name_map = load_ticker_name_map()
        logger.info(f"📦 Ticker im Cache: {len(name_map)}")

        uncached = sorted(s for s in counter if s not in name_map and s not in IGNORED_KEYS)
        if uncached:
            logger.info(f"🆕 Neue Ticker zur Auflösung: {len(uncached)} → {', '.join(uncached)}")

        # Zeige an, welche Ticker aus dem Cache kommen
        cached_tickers = [sym for sym in counter if sym in name_map and sym not in IGNORED_KEYS]
        if cached_tickers:
            logger.info(f"🗃️  Aus Cache: {', '.join(sorted(cached_tickers))}")

        if not uncached:
            logger.info("✅ Alle Ticker bereits bekannt – nichts zu tun.")
            return

        # Versuche lokale Ticker-Liste
        tickers = load_tickerlist()
        symbol_to_name = dict(zip(tickers["Symbol"], tickers["Security Name"]))

        resolved = {}
        fallback_needed = []
        for sym in uncached:
            name = symbol_to_name.get(sym)
            if name:
                resolved[sym] = name
            else:
                fallback_needed.append(sym)
        
        if resolved:
            logger.info(f"✅ Aus lokaler Liste aufgelöst: {', '.join(resolved.keys())}")
        if fallback_needed:
            logger.info(f"⚠️  API-Fallback benötigt für: {', '.join(fallback_needed)}")

        # Fallback: API (parallel)
        if fallback_needed:
            api_resolved = {}
            api_failed = []
            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = {pool.submit(resolve_symbol_parallel, s): s for s in fallback_needed}
                for future in as_completed(futures):
                    sym, name, src = future.result()
                    if name:
                        api_resolved[sym] = (name, src)
                        resolved[sym] = name
                    else:
                        api_failed.append(sym)
            
            if api_resolved:
                for sym, (name, src) in api_resolved.items():
                    logger.info(f"✅ {sym} → {name} ({src} API)")
            if api_failed:
                logger.warning(f"❌ Nicht aufgelöst: {', '.join(api_failed)}")

        if resolved:
            name_map.update(resolved)
            save_ticker_name_map(name_map)
            logger.info(f"💾 Cache aktualisiert: +{len(resolved)} neue Einträge (Gesamt: {len(name_map)})")

            CSV_EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CSV_EXPORT_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Ticker", "Company"])
                for sym in sorted(resolved):
                    writer.writerow([sym, resolved[sym]])
            logger.info(f"📎 Export: {CSV_EXPORT_PATH.name}")
        else:
            logger.info("⚠️  Keine neuen Namen aufgelöst.")

        logger.info("✅ Namensauflösung abgeschlossen.")

    except Exception as e:
        logger.error(f"❌ Fehler bei der Namensauflösung: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    logger.info(f"🔍 Starte Ticker-Namensauflösung (cwd={os.getcwd()})")
    resolve_from_latest_pickle()
