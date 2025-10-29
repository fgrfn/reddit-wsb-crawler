import os
import requests
import pickle
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
import logging

def load_env():
    # Robust .env loading: prefer repo-root/config/.env, fallback to src/config/.env or CWD/config/.env
    base = Path(__file__).resolve().parent
    repo_root = base.parent
    dotenv_path = repo_root / "config" / ".env"
    if not dotenv_path.exists():
        alt = base / "config" / ".env"
        if alt.exists():
            dotenv_path = alt
        else:
            alt2 = Path.cwd() / "config" / ".env"
            if alt2.exists():
                dotenv_path = alt2
    load_dotenv(dotenv_path=str(dotenv_path))
    # Ensure at least a basic logging config so warnings/info are visible when run standalone.
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO)
    return

def load_latest_pickle():
    p = Path(__file__).resolve().parent.parent / "data" / "output" / "pickle"
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"Kein pickle-Ordner gefunden: {p}")
    files = sorted([f for f in p.iterdir() if f.suffix == ".pkl"], reverse=True)
    for file in files:
        try:
            with file.open("rb") as f:
                return pickle.load(f), file.name
        except Exception as e:
            logging.warning(f"Fehler beim Laden {file}: {e}")
    raise FileNotFoundError("Keine .pkl-Dateien gefunden.")

def extract_text(result, ticker):
    texts = []
    # result expected to have a structure like: { 'subreddits': { sr: { 'symbol_hits': {SYM: count}, 'posts': [...] } } }
    for sr_name, sr_data in result.get("subreddits", {}).items():
        try:
            hits = sr_data.get("symbol_hits", {}).get(ticker, 0)
        except Exception:
            hits = 0
        if hits and hits >= 1:
            texts.append(f"r/{sr_name}: {hits} Nennungen")
        # If there are posts stored, include short titles/contexts (best-effort)
        posts = sr_data.get("posts") or sr_data.get("top_posts") or []
        if isinstance(posts, list) and posts:
            added = 0
            for p in posts:
                # p may be a dict with title/url/text or just a string
                title = None
                if isinstance(p, dict):
                    title = p.get("title") or p.get("text") or p.get("body")
                    url = p.get("url") or p.get("permalink")
                else:
                    title = str(p)
                    url = None
                if title:
                    line = f"- {title[:280]}"
                    if url:
                        line += f" ({url})"
                    texts.append(line)
                    added += 1
                if added >= 2:
                    break
    # fallback: some pickles may include a flat 'relevant' dict with counts
    if not texts and isinstance(result.get("relevant"), dict):
        cnt = result["relevant"].get(ticker)
        if cnt:
            texts.append(f"Relevante Nennungen (gesamt): {cnt}")
    return "\n".join([t for t in texts if t])

def summarize_ticker(ticker, context):
    # Hinweis: OpenAI-Aufrufe wurden entfernt — lokale Zusammenfassung (Yahoo/NewsAPI)
    print(f"📄 Erstelle lokale Zusammenfassung für {ticker} ...")
    try:
        # Ensure env loaded (for optional NEWSAPI_KEY)
        load_env()
    except Exception:
        pass

    # 1) price info (may return None fields)
    try:
        price = get_yf_price(ticker)
    except Exception as e:
        logging.warning(f"get_yf_price failed for {ticker}: {e}")
        price = {'regular': None, 'currency': 'USD', 'change': None, 'changePercent': None}

    # 2) news headlines (prefer NewsAPI if configured, otherwise keep empty)
    try:
        headlines = get_yf_news(ticker) or []
    except Exception as e:
        logging.warning(f"get_yf_news failed for {ticker}: {e}")
        headlines = []

    # 3) reddit/context snippets (context param likely from extract_text)
    ctx_lines = [l.strip() for l in (context or "").splitlines() if l.strip()]

    parts = []
    # price sentence
    if price and price.get('regular') is not None:
        p = price['regular']
        cur = price.get('currency', 'USD') or 'USD'
        ch = price.get('change')
        chp = price.get('changePercent')
        price_part = f"Kurs: {p:.2f} {cur}"
        if ch is not None and chp is not None:
            price_part += f" (Δ {ch:+.2f}, {chp:+.2f}%)"
        parts.append(price_part + ".")
    # headlines sentence
    if headlines:
        top = []
        # headlines may be list of dicts (from get_yf_news) or list of strings (NewsAPI path)
        for h in headlines[:2]:
            if isinstance(h, dict):
                title = h.get("title") or h.get("headline") or ""
            else:
                title = str(h)
            if title:
                top.append(title)
        if top:
            parts.append("Aktuelle Headlines: " + " — ".join(top) + ".")
    # context/reddit sentence
    if ctx_lines:
        top_ctx = " | ".join(ctx_lines[:2])
        parts.append("Reddit/Context: " + top_ctx + ".")

    # fallback if nothing collected
    if not parts:
        summary_text = f"Keine Kursdaten oder Nachrichten für {ticker} gefunden."
        return {"summary": summary_text, "news": headlines}

    # Build up to 3 short sentences and respect ~400 char limit
    summary_text = " ".join(parts)[:400]
    return {"summary": summary_text, "news": headlines}

def get_yf_price(symbol):
    import yfinance as yf
    import time
    try:
        ticker = yf.Ticker(symbol)
        price = None
        currency = None
        change = None
        changePercent = None
        pre_market = None
        post_market = None
        market_state = None
        change_1h = None
        change_24h = None
        change_7d = None

        # fast_info / info
        try:
            fi = getattr(ticker, "fast_info", {}) or {}
            if isinstance(fi, dict):
                price = fi.get("lastPrice") or fi.get("regularMarketPrice")
                currency = fi.get("currency")
                pre_market = fi.get("preMarketPrice") or fi.get("preMarketLastPrice")
                post_market = fi.get("postMarketPrice") or fi.get("postMarketLastPrice")
        except Exception:
            fi = {}

        try:
            info = ticker.info or {}
            if price is None:
                price = info.get("regularMarketPrice") or info.get("previousClose")
            currency = currency or info.get("currency", "USD")
            change = info.get("regularMarketChange")
            changePercent = info.get("regularMarketChangePercent")
            pre_market = pre_market or info.get("preMarketPrice")
            post_market = post_market or info.get("postMarketPrice")
            market_state = info.get("marketState") or info.get("market")
        except Exception:
            info = {}

        # Trends: 1h/24h/7d (best-effort, may be None)
        try:
            h1 = ticker.history(period="2h", interval="1m", prepost=True)
            if not h1.empty and len(h1) > 1:
                recent = float(h1["Close"].iloc[-1])
                older = float(h1["Close"].iloc[max(0, len(h1)-61)])
                change_1h = ((recent - older) / older) * 100 if older != 0 else None
        except Exception:
            change_1h = None

        try:
            h24 = ticker.history(period="2d", interval="15m", prepost=True)
            if not h24.empty:
                recent = float(h24["Close"].iloc[-1])
                older = float(h24["Close"].iloc[0])
                change_24h = ((recent - older) / older) * 100 if older != 0 else None
        except Exception:
            change_24h = None

        try:
            h7 = ticker.history(period="8d", interval="1d", prepost=True)
            if not h7.empty:
                recent = float(h7["Close"].iloc[-1])
                older = float(h7["Close"].iloc[0])
                change_7d = ((recent - older) / older) * 100 if older != 0 else None
        except Exception:
            change_7d = None

        return {
            "regular": float(price) if price is not None else None,
            "currency": currency or "USD",
            "change": float(change) if change is not None else None,
            "changePercent": float(changePercent) if changePercent is not None else None,
            "pre": float(pre_market) if pre_market is not None else None,
            "post": float(post_market) if post_market is not None else None,
            "market_state": market_state,
            "change_1h": float(change_1h) if change_1h is not None else None,
            "change_24h": float(change_24h) if change_24h is not None else None,
            "change_7d": float(change_7d) if change_7d is not None else None,
            "symbol": symbol,
            "timestamp": time.time(),
        }
    except Exception as e:
        import logging
        logging.warning(f"Kursdaten-Abfrage für {symbol} fehlgeschlagen: {e}")
        return {
            "regular": None,
            "currency": "USD",
            "change": None,
            "changePercent": None,
            "pre": None,
            "post": None,
            "market_state": None,
            "change_1h": None,
            "change_24h": None,
            "change_7d": None,
            "symbol": symbol,
            "timestamp": None,
        }

def get_yf_news(symbol):
    # Prefer NewsAPI.org when an API key is configured (more reliable headlines)
    NEWSAPI_KEY = os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY")
    NEWSAPI_LANG = os.getenv("NEWSAPI_LANG", "en")
    NEWSAPI_WINDOW_HOURS = int(os.getenv("NEWSAPI_WINDOW_HOURS", "48"))
    if NEWSAPI_KEY:
        try:
            # Try to get a company name from yfinance to improve query
            company = None
            try:
                import yfinance as yf
                info = yf.Ticker(symbol).info or {}
                company = info.get("longName") or info.get("shortName")
            except Exception:
                company = None

            url = "https://newsapi.org/v2/everything"
            # time window
            from datetime import datetime, timedelta
            to_dt = datetime.utcnow()
            from_dt = to_dt - timedelta(hours=NEWSAPI_WINDOW_HOURS)
            from_iso = from_dt.isoformat("T") + "Z"

            def fetch(params):
                try:
                    resp = requests.get(url, params=params, timeout=10)
                    if not resp.ok:
                        return []
                    data = resp.json()
                    articles = data.get("articles", [])
                    headlines = [a.get("title") for a in articles if a.get("title")]
                    # dedupe
                    seen = set()
                    uniq = []
                    for h in headlines:
                        if h and h not in seen:
                            seen.add(h)
                            uniq.append(h)
                    return uniq
                except Exception as e:
                    logging.warning(f"NewsAPI request failed: {e}")
                    return []

            # 1) Try company name in title (best signal)
            if company:
                params = {
                    "qInTitle": company,
                    "language": NEWSAPI_LANG,
                    "from": from_iso,
                    "sortBy": "publishedAt",
                    "pageSize": 20,
                    "apiKey": NEWSAPI_KEY,
                }
                res = fetch(params)
                if res:
                    return res[:20]

            # 2) Try symbol in title
            params = {
                "qInTitle": symbol,
                "language": NEWSAPI_LANG,
                "from": from_iso,
                "sortBy": "publishedAt",
                "pageSize": 20,
                "apiKey": NEWSAPI_KEY,
            }
            res = fetch(params)
            if res:
                return res[:20]

            # 3) Fallback to broader query (company OR symbol)
            query_parts = [symbol]
            if company:
                query_parts.append(f'"{company}"')
            query = " OR ".join(query_parts)
            params = {
                "q": query,
                "language": NEWSAPI_LANG,
                "from": from_iso,
                "sortBy": "publishedAt",
                "pageSize": 20,
                "apiKey": NEWSAPI_KEY,
            }
            res = fetch(params)
            if res:
                return res[:20]
        except Exception as e:
            logging.warning(f"NewsAPI-Abfrage fehlgeschlagen für {symbol}: {e}")

    # Fallback to yfinance news if NewsAPI not configured or fails
    import yfinance as yf
    try:
        ticker_obj = yf.Ticker(symbol)
        news_raw = getattr(ticker_obj, "news", [])[:3]
        news = []
        for n in news_raw:
            news.append({
                "title": n.get("title", ""),
                "source": n.get("publisher", ""),
                "url": n.get("link", "")
            })
        return news
    except Exception as e:
        logging.warning(f"News-Abfrage für {symbol} fehlgeschlagen: {e}")
        return []

def build_context_with_yahoo(ticker, kursdaten, news_headlines=None):
    kurs_str = f"Aktueller Kurs: {kursdaten.get('regular', 'unbekannt')} {kursdaten.get('currency', 'USD')}, " \
               f"Veränderung: {kursdaten.get('change', 'unbekannt')} ({kursdaten.get('changePercent', 'unbekannt')}%)"
    news_str = ""
    if news_headlines:
        news_str = "\nAktuelle Nachrichten:\n" + "\n".join(f"- {headline}" for headline in news_headlines)
    else:
        news_str = "\nKeine aktuellen Nachrichten-Headlines verfügbar."
    return f"{kurs_str}\n{news_str}\nEs liegen keine konkreten Reddit-Diskussionsinhalte vor."

def main():
    load_env()
    result, filename = load_latest_pickle()
    print(f"📥 Verarbeite: {filename}")

    relevant = result.get("relevant", {})
    summaries = {}

    for ticker, count in relevant.items():
        if count < 10:
            continue  # nur „diskussionsreiche“ Ticker
        kursdaten = get_yf_price(ticker)
        news_headlines = get_yf_news(ticker)
        context = build_context_with_yahoo(ticker, kursdaten, news_headlines)
        print(f"{ticker}: News-Kontext für KI:", news_headlines)
        print("Kursdaten:", kursdaten)
        print("KI-Kontext:", context)
        summary = summarize_ticker(ticker, context)
        # summary is now a dict: {"summary": "...", "news": [...]}
        summaries[ticker] = summary

    # 📁 Ergebnisse speichern
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    out_path = f"data/output/summaries/{ts}_ai_trendberichte.md"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        for ticker, summary in summaries.items():
            # write human-readable summary text; include news headlines below
            s_text = summary.get("summary") if isinstance(summary, dict) else str(summary)
            f.write(f"## {ticker}\n{s_text}\n\n")
            news = summary.get("news") if isinstance(summary, dict) else []
            if news:
                f.write("### Headlines\n")
                for n in news[:5]:
                    if isinstance(n, dict):
                        title = n.get("title") or n.get("headline") or ""
                        url = n.get("url") or n.get("link") or ""
                        src = n.get("source") or n.get("publisher") or ""
                        line = f"- {title}"
                        if src:
                            line += f" ({src})"
                        if url:
                            line += f" | {url}"
                    else:
                        line = f"- {str(n)}"
                    f.write(line + "\n")
                f.write("\n")

    print(f"\n✅ Zusammenfassungen gespeichert unter: {out_path}")

if __name__ == "__main__":
    main()
