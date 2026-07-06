"""
Ticker-Erkennung aus Reddit-Texten.

Portiert und verbessert aus v1:
- Regex für explizite Cashtags und vorsichtige implizite Großbuchstaben-Ticker
- Blacklist als Set (O(1) lookup statt O(n))
- Gibt typisierte TickerMention-Objekte zurück
"""

from __future__ import annotations

import re

from wsb_crawler.models import RedditPost, TickerMention

# Ticker-Pattern: $TICKER (case-insensitiv, WSB schreibt oft "$gme") oder
# 2-5 Großbuchstaben ohne $-Präfix. Implizite Treffer werden später bewusst
# strenger gefiltert, weil Reddit-Texte viele normale Großbuchstaben enthalten.
TICKER_PATTERN = re.compile(r"\$([A-Za-z]{1,5})\b|\b([A-Z]{2,5})\b(?=[^a-z]|$)")

# Implizite 2-Buchstaben-Ticker erzeugen extrem viele False Positives
# (AI, EU, US, UK, IT, KI, ...). Daher ohne $ nur ab 3 Zeichen akzeptieren.
MIN_IMPLICIT_TICKER_LEN = 3

_COMMON_WORDS = {
    "A",
    "I",
    "AM",
    "AN",
    "AT",
    "BE",
    "BY",
    "DO",
    "GO",
    "HE",
    "IF",
    "IN",
    "IS",
    "IT",
    "ME",
    "MY",
    "NO",
    "OF",
    "ON",
    "OR",
    "SO",
    "TO",
    "UP",
    "US",
    "WE",
    "ALL",
    "AND",
    "ARE",
    "BUT",
    "BUY",
    "CAN",
    "DID",
    "FOR",
    "GET",
    "GOT",
    "HAD",
    "HAS",
    "HER",
    "HIM",
    "HIS",
    "HOW",
    "ITS",
    "LET",
    "MAY",
    "NEW",
    "NOT",
    "NOW",
    "OLD",
    "ONE",
    "OUR",
    "OUT",
    "OWN",
    "RIP",
    "SAY",
    "SHE",
    "THE",
    "TOO",
    "TRY",
    "TWO",
    "USE",
    "USA",
    "WAS",
    "WHO",
    "WHY",
    "YET",
    "YOU",
    "BEEN",
    "CALL",
    "COME",
    "DOES",
    "DOWN",
    "EACH",
    "EVEN",
    "FROM",
    "GIVE",
    "GOOD",
    "HAVE",
    "HERE",
    "HIGH",
    "INTO",
    "JUST",
    "KEEP",
    "KNOW",
    "LIKE",
    "LOOK",
    "LONG",
    "MAKE",
    "MANY",
    "MORE",
    "MUCH",
    "NEXT",
    "ONLY",
    "OPEN",
    "OVER",
    "PART",
    "PLAY",
    "PUTS",
    "REAL",
    "SAID",
    "SAME",
    "SELL",
    "SEND",
    "SHOW",
    "SOME",
    "SOON",
    "SUCH",
    "TAKE",
    "THAN",
    "THAT",
    "THEM",
    "THEN",
    "THEY",
    "THIS",
    "THUS",
    "TIME",
    "TOLD",
    "TOOK",
    "TRUE",
    "TURN",
    "UPON",
    "VERY",
    "WAIT",
    "WANT",
    "WEEK",
    "WELL",
    "WEN",
    "WENT",
    "WERE",
    "WHAT",
    "WHEN",
    "WITH",
    "WORD",
    "WORK",
    "YEAR",
    "YOUR",
}

_FINANCE_AND_MARKET_NOISE = {
    "ETF",
    "IPO",
    "SEC",
    "CEO",
    "CFO",
    "COO",
    "CTO",
    "LLC",
    "INC",
    "LTD",
    "GDP",
    "CPI",
    "FED",
    "ATH",
    "ATL",
    "EPS",
    "PE",
    "IV",
    "AH",
    "PM",
    "DD",
    "OTM",
    "ITM",
    "ATM",
    "DCA",
    "FUD",
    "FOMO",
    "WSB",
    "RH",
    "HODL",
    "REKT",
    "MOON",
    "MARS",
    "DRAM",
    "RAM",
    "ROI",
    "QNX",
    "LFG",
    "LLM",
}

_REGION_CURRENCY_CRYPTO_NOISE = {
    "EU",
    "UK",
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CAD",
    "AUD",
    "BTC",
    "ETH",
    "KOSPI",
}

_SOCIAL_AND_REDDIT_NOISE = {
    "LOL",
    "LMAO",
    "ROFL",
    "TBH",
    "IMO",
    "OMG",
    "TIL",
    "ELI",
    "TLDR",
    "MODS",
    "EDIT",
    "AFAIK",
    "IIRC",
    "IMHO",
    "YOLO",
    "OP",
    "OC",
    "AMA",
    "LPT",
    "PSA",
    "NSFW",
    "SFW",
}

_GERMAN_WORDS = {
    "DE",
    "AG",
    "GE",
    "KI",
    "DER",
    "DIE",
    "DAS",
    "EIN",
    "EINE",
    "UND",
    "MIT",
    "AUF",
    "BEI",
    "VON",
    "ZUR",
    "ZUM",
    "FÜR",
    "BIS",
    "ICH",
    "WIR",
    "SIE",
    "HAT",
    "IST",
    "WAR",
    "ABER",
    "AUCH",
    "NOCH",
    "NACH",
    "WENN",
    "DANN",
    "MICH",
    "SICH",
    "MEHR",
    "KEIN",
    "NEUE",
    "JETZT",
    "SCHON",
    "IMMER",
}

# Blacklist: häufige Wörter die fälschlicherweise als Ticker erkannt werden.
BLACKLIST: frozenset[str] = frozenset(
    _COMMON_WORDS
    | _FINANCE_AND_MARKET_NOISE
    | _REGION_CURRENCY_CRYPTO_NOISE
    | _SOCIAL_AND_REDDIT_NOISE
    | _GERMAN_WORDS
)

# Maximale Kontextlänge (Zeichen rund um den Ticker-Fund)
CONTEXT_WINDOW = 100


def extract_tickers(post: RedditPost) -> list[TickerMention]:
    """
    Extrahiert alle Ticker-Erwähnungen aus einem Post/Kommentar.

    Priorisiert $TICKER-Format (explizit gemeint) gegenüber reinen
    Großbuchstaben-Sequenzen (könnten Abkürzungen sein).

    Gibt pro Post jede Ticker+Post-ID-Kombination nur einmal zurück
    (Dedup innerhalb eines Posts), zählt aber mehrfache Nennungen
    über separate Posts hinweg.
    """
    text = f"{post.title} {post.text}".strip()
    if not text:
        return []

    found: set[str] = set()  # Dedup innerhalb dieses Posts
    mentions: list[TickerMention] = []

    for match in TICKER_PATTERN.finditer(text):
        # Gruppe 1: $TICKER (explizit), Gruppe 2: TICKER (implizit)
        ticker = (match.group(1) or match.group(2)).upper()
        is_explicit = match.group(1) is not None

        if ticker in BLACKLIST:
            continue
        # Einzelbuchstaben nur mit explizitem $-Präfix ("$F" ja, "F" nein)
        if len(ticker) < 2 and not is_explicit:
            continue
        if ticker in found:
            continue

        # Implizite Ticker (ohne $) sind deutlich unsicherer als Cashtags.
        # 2-Buchstaben-Treffer sind auf Reddit fast immer Sprache/Abkürzungen.
        if not is_explicit and len(ticker) < MIN_IMPLICIT_TICKER_LEN:
            continue

        # Implizite Ticker (ohne $) nur wenn nicht rein numerisch
        if not is_explicit and ticker.isdigit():
            continue

        found.add(ticker)

        # Kontext extrahieren
        start = max(0, match.start() - CONTEXT_WINDOW // 2)
        end = min(len(text), match.end() + CONTEXT_WINDOW // 2)
        context = text[start:end].replace("\n", " ").strip()

        mentions.append(
            TickerMention(
                ticker=ticker,
                post_id=post.id,
                subreddit=post.subreddit,
                context=context,
                score=post.score,
                created_utc=post.created_utc,
            )
        )

    return mentions


def aggregate_mentions(mentions: list[TickerMention]) -> dict[str, int]:
    """
    Aggregiert eine Liste von TickerMentions zu einem {ticker: count} Dict.
    Sortiert nach Häufigkeit (häufigste zuerst).
    """
    counts: dict[str, int] = {}
    for mention in mentions:
        counts[mention.ticker] = counts.get(mention.ticker, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
