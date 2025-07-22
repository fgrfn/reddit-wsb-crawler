import os
import time
import pickle
import requests
import yfinance as yf
import pandas as pd
import logging
from pathlib import Path

TICKER_CACHE_PATH = os.path.join("data", "input", "ticker_name_map.pkl")
TICKER_CSV = Path("data/input/all_tickers.csv")

# 📦 Lokaler Cache laden
def load_ticker_name_map():
    if os.path.exists(TICKER_CACHE_PATH):
        with open(TICKER_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    return {}

# 💾 Namen in Cache speichern
def save_ticker_name_map(name_map):
    with open(TICKER_CACHE_PATH, "wb") as f:
        pickle.dump(name_map, f)

# 🧠 Der Multi-Resolver
def resolve_ticker_name(symbol, cache=None):
    if cache is None:
        cache = load_ticker_name_map()

    # 1. Suche in der aktuellen Tickerliste
    if TICKER_CSV.exists():
        df = pd.read_csv(TICKER_CSV)
        row = df[df["Symbol"] == symbol]
        if not row.empty:
            name = row.iloc[0]["Security Name"]
            if name and name != symbol:
                cache[symbol] = name
                save_ticker_name_map(cache)
                return symbol, name

    # 🚫 Bereits bekannt?
    if symbol in cache and cache[symbol]:
        return symbol, cache[symbol]

    # 🧪 Versuch 1: yfinance
    try:
        info = yf.Ticker(symbol).info
        name = info.get("longName") or info.get("shortName")
        if name and name != symbol:
            cache[symbol] = name
            save_ticker_name_map(cache)
            return symbol, name
    except Exception as e:
        logging.warning(f"yfinance-Fehler für {symbol}: {e}")

    # 🛟 Versuch 2: Yahoo Search API
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}"
        response = requests.get(url, headers=headers, timeout=5)
        if response.ok:
            data = response.json()
            for result in data.get("quotes", []):
                if result.get("symbol") == symbol and result.get("shortname"):
                    name = result["shortname"]
                    cache[symbol] = name
                    save_ticker_name_map(cache)
                    return symbol, name
    except Exception as e:
        logging.warning(f"Yahoo-API-Fehler für {symbol}: {e}")

    # 🔄 Versuch 3: Alpha Vantage (wenn API-Key gesetzt)
    ALPHA_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
    if ALPHA_KEY:
        try:
            url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={symbol}&apikey={ALPHA_KEY}"
            response = requests.get(url, timeout=5)
            if response.ok:
                matches = response.json().get("bestMatches", [])
                for match in matches:
                    if match["1. symbol"] == symbol:
                        name = match["2. name"]
                        cache[symbol] = name
                        save_ticker_name_map(cache)
                        return symbol, name
        except Exception as e:
            logging.warning(f"AlphaVantage-Fehler für {symbol}: {e}")

    # ❌ Nichts gefunden
    return symbol, None
