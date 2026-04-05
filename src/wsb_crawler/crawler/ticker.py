"""
Ticker-Erkennung aus Reddit-Texten.

Portiert und verbessert aus v1:
- Gleiche Regex-Basis (bewährt)
- Blacklist als Set (O(1) lookup statt O(n))
- Gibt typisierte TickerMention-Objekte zurück
"""

from __future__ import annotations

import re
from datetime import datetime

from wsb_crawler.models import RedditPost, TickerMention

# Ticker-Pattern: 1-5 Großbuchstaben, optional mit $ davor
# Negative Lookahead schließt bekannte Abkürzungen aus
TICKER_PATTERN = re.compile(r"\$([A-Z]{1,5})\b|\b([A-Z]{2,5})\b(?=[^a-z]|$)")

# Blacklist: häufige Wörter die fälschlicherweise als Ticker erkannt werden
# Aus v1 portiert + erweitert
BLACKLIST: frozenset[str] = frozenset(
    {
        # Englische Wörter
        "A", "I", "AM", "AN", "AT", "BE", "BY", "DO", "GO", "HE", "IF", "IN",
        "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US",
        "WE", "ALL", "AND", "ARE", "BUT", "CAN", "DID", "FOR", "GET", "GOT",
        "HAD", "HAS", "HER", "HIM", "HIS", "HOW", "ITS", "LET", "MAY", "NEW",
        "NOT", "NOW", "OLD", "ONE", "OUR", "OUT", "OWN", "SAY", "SHE", "THE",
        "TOO", "TWO", "USE", "WAS", "WHO", "WHY", "YET", "YOU",
        "BEEN", "CALL", "COME", "DOES", "DOWN", "EACH", "EVEN", "FROM", "GIVE",
        "GOOD", "HAVE", "HERE", "HIGH", "INTO", "JUST", "KEEP", "KNOW", "LIKE",
        "LOOK", "LONG", "MAKE", "MANY", "MORE", "MUCH", "NEXT", "ONLY", "OPEN",
        "OVER", "PART", "PLAY", "PUTS", "REAL", "SAID", "SAME", "SELL", "SEND",
        "SHOW", "SOME", "SOON", "SUCH", "TAKE", "THAN", "THAT", "THEM", "THEN",
        "THEY", "THIS", "THUS", "TIME", "TOLD", "TOOK", "TRUE", "TURN", "UPON",
        "VERY", "WAIT", "WANT", "WEEK", "WELL", "WENT", "WERE", "WHAT", "WHEN",
        "WITH", "WORD", "WORK", "YEAR", "YOUR",
        # Finance-Begriffe (keine Ticker!)
        "ETF", "IPO", "SEC", "CEO", "CFO", "COO", "CTO", "LLC", "INC", "LTD",
        "GDP", "CPI", "FED", "ATH", "ATL", "LOL", "TBH", "IMO", "EPS", "PE",
        "AH", "PM", "DD", "OTM", "ITM", "ATM", "DCA", "YOLO", "FUD", "FOMO",
        "WSB", "RH", "WTF", "WTH", "OMG", "TIL", "ELI", "TLDR", "MODS",
        "EDIT", "AFAIK", "IIRC", "IMHO", "HODL", "REKT", "MOON", "MARS",
        # Bekannte Subreddit/Reddit-Begriffe
        "OP", "OC", "AMA", "TIL", "LPT", "PSA", "NSFW", "SFW",
        # Deutsche Wörter (für wallstreetbetsGER)
        "DE", "AG", "GE", "DER", "DIE", "DAS", "EIN", "EINE", "UND", "MIT",
        "AUF", "BEI", "VON", "ZUR", "ZUM", "FÜR", "BIS", "ICH", "WIR", "SIE",
        "HAT", "IST", "WAR", "ABER", "AUCH", "NOCH", "NACH", "WENN", "DANN",
        "MICH", "SICH", "MEHR", "KEIN", "NEUE", "JETZT", "SCHON", "IMMER",
    }
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

    found: set[str] = set()   # Dedup innerhalb dieses Posts
    mentions: list[TickerMention] = []

    for match in TICKER_PATTERN.finditer(text):
        # Gruppe 1: $TICKER (explizit), Gruppe 2: TICKER (implizit)
        ticker = (match.group(1) or match.group(2)).upper()
        is_explicit = match.group(1) is not None

        if ticker in BLACKLIST:
            continue
        if len(ticker) < 2:
            continue
        if ticker in found:
            continue

        # Implizite Ticker (ohne $) nur wenn ≥ 2 Zeichen und nicht rein numerisch
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
