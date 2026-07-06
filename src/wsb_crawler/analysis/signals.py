"""
Signalqualität: Engagement- und Sentiment-Auswertung pro Ticker.

Aus den Einzel-Nennungen eines Laufs (mit Post-Score und Umgebungstext)
werden pro Ticker Qualitätssignale abgeleitet:

- **Engagement** — aus den Post-Scores (eine Nennung in einem 2.000-Upvote-Post
  wiegt mehr als in einem Kommentar mit 0).
- **Sentiment** — einfaches Bull/Bear-Keyword-Zählen im ~100-Zeichen-Kontext
  rund um den Ticker (WSB-Slang + Emojis).

Bewusst heuristisch und erklärbar — kein ML. Der Spike-Auslöser bleibt die
reine Nennungszahl; diese Signale wirken nur auf Ranking, Confidence und
Alert-Anzeige.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wsb_crawler.models import TickerMention, TickerSignal

# WSB-typische Wörter. Bewusst kompakt gehalten — lieber wenige klare Treffer
# als viele mehrdeutige. Wortgrenzen verhindern Teiltreffer ("call" in "called").
_BULL_WORDS = frozenset(
    {
        "call",
        "calls",
        "buy",
        "buying",
        "bought",
        "long",
        "longs",
        "moon",
        "mooning",
        "rocket",
        "squeeze",
        "hold",
        "holding",
        "hodl",
        "yolo",
        "bull",
        "bullish",
        "breakout",
        "pump",
        "pumping",
        "tendies",
        "undervalued",
        "gains",
        "green",
        "printing",
        "diamond",
    }
)
_BEAR_WORDS = frozenset(
    {
        "put",
        "puts",
        "sell",
        "selling",
        "sold",
        "short",
        "shorts",
        "shorting",
        "dump",
        "dumping",
        "crash",
        "crashing",
        "bear",
        "bearish",
        "drop",
        "dropping",
        "red",
        "bag",
        "bagholder",
        "overvalued",
        "rug",
        "rugpull",
        "tank",
        "tanking",
        "puke",
        "dead",
    }
)
# Emojis sind keine Wort-Zeichen → separat als Substring geprüft.
_BULL_EMOJI = ("🚀", "🌙", "💎", "🐂", "📈", "🤑")
_BEAR_EMOJI = ("🐻", "📉", "💀", "🧸")

_BULL_RE = re.compile(r"\b(" + "|".join(map(re.escape, _BULL_WORDS)) + r")\b")
_BEAR_RE = re.compile(r"\b(" + "|".join(map(re.escape, _BEAR_WORDS)) + r")\b")


def score_sentiment(text: str) -> tuple[int, int]:
    """Zählt bullische und bearische Treffer in einem Textausschnitt."""
    lowered = text.lower()
    bull = len(_BULL_RE.findall(lowered)) + sum(lowered.count(e) for e in _BULL_EMOJI)
    bear = len(_BEAR_RE.findall(lowered)) + sum(lowered.count(e) for e in _BEAR_EMOJI)
    return bull, bear


@dataclass
class _Acc:
    count: int = 0
    total_score: int = 0
    max_score: int = 0
    bull: int = 0
    bear: int = 0


def compute_signals(mentions: list[TickerMention]) -> dict[str, TickerSignal]:
    """Aggregiert Einzel-Nennungen zu {ticker: TickerSignal}."""
    acc: dict[str, _Acc] = {}
    for m in mentions:
        a = acc.setdefault(m.ticker, _Acc())
        a.count += 1
        a.total_score += m.score
        a.max_score = max(a.max_score, m.score)
        bull, bear = score_sentiment(m.context)
        a.bull += bull
        a.bear += bear

    return {
        ticker: TickerSignal(
            ticker=ticker,
            mention_count=a.count,
            total_score=a.total_score,
            max_score=a.max_score,
            bull_hits=a.bull,
            bear_hits=a.bear,
        )
        for ticker, a in acc.items()
    }
