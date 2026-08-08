"""
Erfolgskontrolle für gesendete Alerts.

Zu jedem Alert ist der Kurs beim Versand gespeichert. Dieses Modul misst den
Kurs 1 h und 24 h später nach und schreibt ihn zurück — damit lässt sich später
beantworten, ob ein Alert-Grund überhaupt etwas taugt, statt Schwellwerte nach
Gefühl zu drehen.

Läuft am Ende jedes Crawls und ist absichtlich sparsam: pro Lauf und Zeitfenster
nur eine begrenzte Anzahl Ticker, gebündelt über den gedrosselten Bulk-Abruf.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from wsb_crawler.enrichment.prices import get_prices_bulk
from wsb_crawler.storage.database import OUTCOME_WINDOWS

if TYPE_CHECKING:
    from wsb_crawler.storage.database import Database

# Obergrenze je Lauf und Fenster — die Kursquelle drosselt aggressiv, und
# ausstehende Messungen holt der nächste Lauf nach.
MAX_PER_RUN = 25


async def update_alert_outcomes(db: Database, limit: int = MAX_PER_RUN) -> dict[int, int]:
    """Misst fällige Alert-Kurse nach. Gibt {fenster_stunden: anzahl} zurück."""
    updated: dict[int, int] = {}

    for window_hours in sorted(OUTCOME_WINDOWS):
        pending = await db.get_alerts_awaiting_outcome(window_hours, limit=limit)
        if not pending:
            continue

        tickers = [row["ticker"] for row in pending]
        try:
            prices = await get_prices_bulk(tickers)
        except Exception as e:
            logger.warning(f"Erfolgskontrolle ({window_hours}h): Kursabruf fehlgeschlagen: {e}")
            continue

        count = 0
        for row in pending:
            price_data = prices.get(row["ticker"])
            current = price_data.primary_price if price_data else None
            if current is None:
                continue  # kein Kurs verfügbar — nächster Lauf versucht es erneut
            await db.save_alert_outcome(row["id"], window_hours, current)
            count += 1

        if count:
            updated[window_hours] = count
            logger.info(f"Erfolgskontrolle: {count} Alert(s) nach {window_hours}h nachgemessen")

    return updated
