"""
ISIN-Auflösung für Ticker (`GME` → `US36467W1099`).

Warum überhaupt: US-Ticker sind an europäischen Brokern (Trade Republic,
Scalable, Revolut) nutzlos — die suchen über die ISIN. Steht sie im Alert,
lässt sie sich in jeden Broker kopieren, ohne dass wir uns auf undokumentierte
Deep-Link-Formate verlassen müssen, die jederzeit brechen können.

Quelle ist derselbe öffentliche Suggest-Endpunkt, den auch yfinance für seine
(als experimentell markierte) `Ticker.isin`-Eigenschaft verwendet — nur hier
async, mit eigener Auswertung und Prüfziffernkontrolle. Eine offizielle,
kostenlose Ticker→ISIN-Quelle gibt es nicht: OpenFIGI bildet Kennungen nur
*auf* FIGI ab, und CUSIP (aus dem sich US-ISINs ableiten) ist lizenzpflichtig.

Deshalb strikt best-effort: Eine ISIN ist ein Zusatz im Alert, nie eine
Voraussetzung. Jeder Fehler endet in `None`, und der Alert geht trotzdem raus.
Ergebnisse landen dauerhaft in der DB — eine ISIN ändert sich praktisch nie,
also wird pro Ticker genau einmal nachgeschlagen und nicht pro Alert.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import httpx
from loguru import logger

if TYPE_CHECKING:
    from wsb_crawler.storage.database import Database

_db: Database | None = None

SEARCH_URL = "https://markets.businessinsider.com/ajax/SearchController_Suggest"

# Erfolglose Suchen nach dieser Zeit erneut versuchen: ein Ticker kann später
# gelistet werden, und ein einmaliger Ausfall der Quelle darf nicht dauerhaft
# als "gibt es nicht" festgeschrieben werden.
NEGATIVE_RETRY_DAYS = 30

REQUEST_TIMEOUT_SECONDS = 8.0

# Die Antwort enthält Einträge der Form "TICKER|ISIN|…"
_ISIN_PATTERN = "[A-Z]{2}[A-Z0-9]{9}[0-9]"
_ISIN_RE = re.compile(f"^{_ISIN_PATTERN}$")


def set_database(db: Database) -> None:
    global _db
    _db = db


def is_valid_isin(value: str) -> bool:
    """Prüft Format **und** Prüfziffer einer ISIN.

    Die Prüfziffer ist hier kein Selbstzweck: Wir lesen die ISIN aus einer
    HTML-/Text-Antwort, deren Format sich ohne Vorwarnung ändern kann. Eine
    falsch geparste Zeichenkette fällt so auf, statt als vermeintliche ISIN im
    Alert zu landen — eine falsche ISIN wäre schlimmer als gar keine.
    """
    if not _ISIN_RE.match(value):
        return False
    # Buchstaben zu Zahlen expandieren (A=10 … Z=35), dann Luhn-Prüfung
    digits = "".join(str(int(c, 36)) for c in value[:-1])
    total = 0
    # Von rechts: jede zweite Ziffer verdoppeln
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    check_digit = (10 - total % 10) % 10
    return check_digit == int(value[-1])


def _extract_isin(payload: str, ticker: str) -> str | None:
    """Zieht die ISIN zum gesuchten Ticker aus der Suggest-Antwort."""
    match = re.search(f'"{re.escape(ticker)}\\|({_ISIN_PATTERN})', payload)
    if not match:
        return None
    candidate = match.group(1)
    if not is_valid_isin(candidate):
        logger.debug(f"ISIN-Kandidat für {ticker} verworfen (Prüfziffer): {candidate}")
        return None
    return candidate


async def _lookup(ticker: str, company_name: str | None = None) -> str | None:
    """Fragt den Suggest-Endpunkt ab. Gibt bei jedem Fehler None zurück."""
    # Mit Firmennamen trifft die Suche zuverlässiger als mit dem nackten Kürzel
    query = company_name or ticker
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(SEARCH_URL, params={"max_results": 25, "query": query})
            response.raise_for_status()
            payload = response.text
    except Exception as e:
        logger.debug(f"ISIN-Abruf für {ticker} fehlgeschlagen: {e}")
        return None

    isin = _extract_isin(payload, ticker)
    # Der Firmenname kann auf einen anderen Ticker führen (Zweitnotierungen);
    # in dem Fall lohnt der zweite Versuch mit dem Kürzel selbst.
    if isin is None and company_name:
        return await _lookup(ticker)
    return isin


async def get_isin(ticker: str, company_name: str | None = None) -> str | None:
    """ISIN zu einem Ticker — aus der DB, sonst per Abruf (und dann gespeichert)."""
    if _db is None:
        return None

    try:
        cached = await _db.get_cached_isin(ticker, retry_after_days=NEGATIVE_RETRY_DAYS)
    except Exception as e:
        logger.debug(f"ISIN-Cache für {ticker} nicht lesbar: {e}")
        cached = None
    if cached is not None:
        return cached.isin

    try:
        isin = await _lookup(ticker, company_name)
    except Exception as e:
        # Die ISIN ist ein Zusatz — sie darf die Anreicherung nie abbrechen
        logger.debug(f"ISIN-Suche für {ticker} abgebrochen: {e}")
        return None

    try:
        await _db.save_isin(ticker, isin)
    except Exception as e:
        logger.debug(f"ISIN für {ticker} nicht speicherbar: {e}")

    if isin:
        logger.info(f"ISIN aufgelöst: {ticker} = {isin}")
    return isin


async def get_isins_bulk(
    tickers: list[str], company_names: dict[str, str | None] | None = None
) -> dict[str, str | None]:
    """ISINs für mehrere Ticker. Nacheinander — die Quelle ist kein Massendienst."""
    names = company_names or {}
    results: dict[str, str | None] = {}
    for ticker in dict.fromkeys(tickers):
        results[ticker] = await get_isin(ticker, names.get(ticker))
        await asyncio.sleep(0)  # Kontrolle abgeben, damit der Loop nicht blockiert
    return {ticker: results.get(ticker) for ticker in tickers}
