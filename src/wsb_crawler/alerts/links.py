"""
Externe Links zu einem Ticker (Kursseite, Chart, Community, Reddit-Suche).

Bewusst statische URL-Muster statt API-Aufrufe: die Links sollen im Alert
sofort verfügbar sein, ohne dass ein weiterer Netzwerk-Call den Versand
verzögern oder scheitern lassen kann. Ob die Zielseite den Ticker kennt,
entscheidet der Anbieter — ein toter Link ist harmloser als ein fehlender
Alert.
"""

from __future__ import annotations

from urllib.parse import quote

_YAHOO = "https://finance.yahoo.com/quote/{ticker}"
_TRADINGVIEW = "https://www.tradingview.com/symbols/{ticker}/"
_STOCKTWITS = "https://stocktwits.com/symbol/{ticker}"
_REDDIT_SEARCH = "https://www.reddit.com/r/{subs}/search/?q=%24{ticker}&restrict_sr=1&sort=new"


def _safe(ticker: str) -> str:
    """Normalisiert einen Ticker für die Verwendung in einer URL."""
    return quote(ticker.strip().upper(), safe="")


def quote_url(ticker: str) -> str:
    """Yahoo-Finance-Kursseite — die Hauptquelle des Crawlers."""
    return _YAHOO.format(ticker=_safe(ticker))


def chart_url(ticker: str) -> str:
    return _TRADINGVIEW.format(ticker=_safe(ticker))


def community_url(ticker: str) -> str:
    return _STOCKTWITS.format(ticker=_safe(ticker))


def reddit_search_url(ticker: str, subreddits: list[str] | None = None) -> str:
    """Reddit-Suche nach `$TICKER` in den überwachten Subreddits.

    Mehrere Subreddits werden als Multireddit (`a+b`) verknüpft, damit der
    Link genau die Quellen zeigt, aus denen der Alert stammt.
    """
    # removeprefix statt lstrip: lstrip("r/") würde aus "robinhood" "obinhood" machen
    subs = [s.strip().removeprefix("r/").strip("/") for s in (subreddits or []) if s.strip()]
    joined = "+".join(quote(s, safe="") for s in subs) or "wallstreetbets"
    return _REDDIT_SEARCH.format(subs=joined, ticker=_safe(ticker))


def link_targets(ticker: str, subreddits: list[str] | None = None) -> list[tuple[str, str]]:
    """Alle Links als (Label, URL) in Anzeige-Reihenfolge."""
    return [
        ("Yahoo Finance", quote_url(ticker)),
        ("Chart", chart_url(ticker)),
        ("Stocktwits", community_url(ticker)),
        ("Reddit", reddit_search_url(ticker, subreddits)),
    ]
