"""Ticker-Listen-Verwaltung: Download und Bereinigung von Ticker-Daten.

Lädt Tickerlisten von NASDAQ, NYSE und lokalen Quellen (DE/EU),
bereinigt sie und speichert sie als CSV und Pickle.
"""
from pathlib import Path
import pandas as pd
import logging
import pickle

logger = logging.getLogger(__name__)

# Basisverzeichnis bestimmen (eine Ebene über src)
BASE_DIR = Path(__file__).parent.parent

# Quellen für die Ticker-Listen
NASDAQ_URL = "https://datahub.io/core/nasdaq-listings/r/nasdaq-listed-symbols.csv"
NYSE_LOCAL = BASE_DIR / "data/input/nyse-listed-symbols.csv"
DE_LOCAL = BASE_DIR / "data/input/de-listed-symbols.xlsx"

TICKER_CSV = BASE_DIR / "data/input/all_tickers.csv"
SYMBOLS_PKL = BASE_DIR / "data/input/symbols_list.pkl"

def download_and_clean_tickerlist() -> pd.DataFrame:
    """Lädt Tickerlisten von NASDAQ (online), NYSE und DE/EU (lokal).
    
    Bereinigt die Daten von ETFs, Fonds, SPACs etc. und speichert
    das Ergebnis als CSV und Symbol-Liste als Pickle.
    
    Returns:
        pd.DataFrame: Bereinigte Tickerliste mit Spalten Symbol, Security Name, Exchange
    """
    # NASDAQ laden
    logger.info("⬇️ Lade aktuelle NASDAQ-Tickerliste ...")
    nasdaq = pd.read_csv(NASDAQ_URL)
    nasdaq = nasdaq[["Symbol", "Company Name"]]
    nasdaq = nasdaq.rename(columns={"Company Name": "Security Name"})
    nasdaq["Exchange"] = "NASDAQ"
    logger.info(f"NASDAQ: {len(nasdaq)} Einträge geladen.")
    print(f"NASDAQ: {len(nasdaq)} Einträge geladen.")

    if "Symbol" not in nasdaq.columns or "Security Name" not in nasdaq.columns:
        logger.error(f"❌ NASDAQ-Datei hat unerwartete Spalten: {list(nasdaq.columns)}")
        nasdaq = pd.DataFrame(columns=["Symbol", "Security Name", "Exchange"])

    # NYSE laden (lokale Datei)
    if NYSE_LOCAL.exists():
        logger.info("⬇️ Lade NYSE-Tickerliste (lokal) ...")
        nyse = pd.read_csv(NYSE_LOCAL)
        # Passe die Spaltennamen ggf. an!
        if "Company Name" in nyse.columns:
            nyse = nyse.rename(columns={"Company Name": "Security Name"})
        nyse = nyse[["Symbol", "Security Name"]]
        nyse["Exchange"] = "NYSE"
        logger.info(f"NYSE: {len(nyse)} Einträge geladen.")
    else:
        nyse = pd.DataFrame(columns=["Symbol", "Security Name", "Exchange"])
        logger.warning("⚠️ Keine NYSE-Liste gefunden!")

    # Deutschland/Europa laden (lokale Datei)
    if DE_LOCAL.exists():
        logger.info("⬇️ Lade DE/EU-Tickerliste (lokal, Excel, Blatt 'Prime Standard') ...")
        # Header in Zeile 8 (header=7), weil Zeile 1-7 nur Titel und Infos enthalten
        de = pd.read_excel(
            DE_LOCAL,
            sheet_name="Prime Standard",
            header=7  # Zeile 8 ist die Kopfzeile (0-basiert)
        )
        # Nur relevante Spalten extrahieren und umbenennen
        if "Trading Symbol" in de.columns and "Company" in de.columns:
            de = de.rename(columns={"Trading Symbol": "Symbol", "Company": "Security Name"})
            de["Exchange"] = "DE/EU"
            de = de[["Symbol", "Security Name", "Exchange"]]
            logger.info(f"DE/EU: {len(de)} Einträge geladen.")
        else:
            logger.error(
                f"❌ Erwartete Spalten 'Trading Symbol', 'Company' nicht gefunden! Vorhandene Spalten: {list(de.columns)}"
            )
            de = pd.DataFrame(columns=["Symbol", "Security Name", "Exchange"])
    else:
        de = pd.DataFrame(columns=["Symbol", "Security Name", "Exchange"])
        logger.warning("⚠️ Keine DE/EU-Liste gefunden!")

    # NYSE: Exchange-Spalte ergänzen, falls Datei nicht existiert
    if not NYSE_LOCAL.exists():
        nyse["Exchange"] = "NYSE"

    # DE/EU: Exchange-Spalte ergänzen, falls Datei nicht existiert
    if not DE_LOCAL.exists():
        de["Exchange"] = "DE/EU"

    # Alle zusammenführen
    tickers = pd.concat([nasdaq, nyse, de], ignore_index=True)
    logger.info(f"Gesamt vor Bereinigung: {len(tickers)} Ticker.")

    # Bereinigen
    mask = ~tickers["Security Name"].str.contains(
        "ETF|Fund|Trust|Warrant|Test|Notes|Depositary|SPAC", case=False, na=False
    )
    tickers = tickers[mask]
    logger.info(f"Nach Bereinigung: {len(tickers)} Ticker.")

    tickers = tickers.drop_duplicates(subset="Symbol")
    logger.info(f"Nach Entfernen von Duplikaten: {len(tickers)} Ticker.")

    TICKER_CSV.parent.mkdir(parents=True, exist_ok=True)
    tickers.to_csv(TICKER_CSV, index=False)
    logger.info(f"Tickerliste gespeichert unter: {TICKER_CSV.resolve()}")

    # Symbol-Liste als Pickle speichern
    SYMBOLS_PKL.parent.mkdir(parents=True, exist_ok=True)
    with open(SYMBOLS_PKL, "wb") as f:
        pickle.dump(list(tickers["Symbol"]), f)
    logger.info(f"Symbol-Liste gespeichert unter: {SYMBOLS_PKL.resolve()}")

    return tickers

def load_tickerlist() -> pd.DataFrame:
    """Lädt die Tickerliste aus CSV oder erstellt sie neu.
    
    Returns:
        pd.DataFrame: Tickerliste
    """
    if not TICKER_CSV.exists():
        return download_and_clean_tickerlist()
    return pd.read_csv(TICKER_CSV)
