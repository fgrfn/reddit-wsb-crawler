import openai
import os
import requests
import pickle
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict
import logging

openai.api_key = None

def load_env():
    load_dotenv(dotenv_path="config/.env")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("❌ OPENAI_API_KEY fehlt in config/.env")
    global openai
    openai.api_key = key

def load_latest_pickle():
    files = sorted(os.listdir("data/output/pickle"), reverse=True)
    for file in files:
        if file.endswith(".pkl"):
            with open(f"data/output/pickle/{file}", "rb") as f:
                return pickle.load(f), file
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
    print(f"📄 Sende {ticker}-Kontext an OpenAI ...")
    # Ensure OpenAI key is present. Try to load if not set and provide a
    # graceful fallback when OpenAI is not configured.
    if not openai.api_key:
        try:
            load_env()
        except Exception as e:
            logging.warning(f"OpenAI nicht konfiguriert: {e} — Summary wird übersprungen.")
            return f"🛑 OpenAI nicht konfiguriert — Zusammenfassung übersprungen für {ticker}."
    system_msg = (
        f"Du bist ein erfahrener Finanzanalyst. Analysiere Kursdaten, Nachrichten und ggf. Reddit-Stimmung zur Aktie {ticker}."
    )
    prompt = (
        f"Fasse die wichtigsten Erkenntnisse zur Aktie {ticker} in maximal 3 Sätzen und höchstens 400 Zeichen zusammen:\n"
        f"{context}\n\n"
        f"- Wie hat sich der Kurs von {ticker} zuletzt entwickelt?\n"
        f"- Gibt es relevante Nachrichten zu {ticker}?\n"
        f"Falls keine Kursbewegung oder Nachrichten vorliegen, gib eine kurze allgemeine Einschätzung ab."
        f"Nutze die im Kontext genannten Daten und Headlines zu {ticker} und vermeide Fantasie."
    )
    try:
        # Use the newer Chat Completions API if available, but keep a generic
        # call that works with common OpenAI client versions. Prefer `chat.completions`.
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=250,
        )
        summary = response.choices[0].message.content.strip()
        # Kosten grob berechnen
        usage = response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens
        # GPT-4o Preise (Stand Juli 2025, ggf. anpassen!)
        cost = (input_tokens / 1000 * 0.005) + (output_tokens / 1000 * 0.015)
        logging.info(f"OpenAI-Kosten für {ticker}: {cost:.4f} USD (Input: {input_tokens}, Output: {output_tokens})")
        # Separate Kostenstatistik
        with open("logs/openai_costs.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()},COST,{cost:.4f},TOKENS,{input_tokens},{output_tokens},{ticker}\n")
        log_crawl = "logs/openai_costs_crawl.log"
        log_day = "logs/openai_costs_day.log"
        log_total = "logs/openai_costs_total.log"

        log_entry = f"{datetime.now().isoformat()},COST,{cost:.4f},TOKENS,{input_tokens},{output_tokens},{ticker}\n"

        for log_path in [log_crawl, log_day, log_total]:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
        if not summary:
            summary = f"Keine relevanten Kursbewegungen oder Nachrichten zu {ticker} im angegebenen Zeitraum."
        return summary[:400]
    except Exception as e:
        logging.error(f"OpenAI-Fehler für {ticker}: {e}")
        # Return a short, friendly message so downstream code still has a string
        # to show instead of completely missing content.
        return f"❌ OpenAI-Fehler für {ticker}: {str(e)}"

def get_yf_price(symbol):
    import yfinance as yf
    try:
        ticker = yf.Ticker(symbol)
        price = None
        currency = None
        change = None
        changePercent = None

        # 1) Try fast_info (more reliable / lightweight)
        try:
            fi = getattr(ticker, 'fast_info', None) or {}
            if isinstance(fi, dict):
                price = fi.get('lastPrice') or fi.get('regularMarketPrice')
                currency = fi.get('currency')
        except Exception:
            fi = {}

        # 2) fallback to info
        if price is None:
            try:
                info = ticker.info or {}
                price = info.get('regularMarketPrice') or info.get('previousClose')
                currency = currency or info.get('currency', 'USD')
                change = info.get('regularMarketChange')
                changePercent = info.get('regularMarketChangePercent')
            except Exception:
                info = {}

        # 3) fallback to history
        if price is None:
            try:
                hist = ticker.history(period='2d')
                if not hist.empty:
                    price = float(hist['Close'].iloc[-1])
                    prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else None
                    if prev:
                        change = price - prev
                        changePercent = (change / prev) * 100 if prev != 0 else None
            except Exception:
                pass

        return {
            'regular': float(price) if price is not None else None,
            'currency': currency or 'USD',
            'change': float(change) if change is not None else None,
            'changePercent': float(changePercent) if changePercent is not None else None,
            'symbol': symbol,
        }
    except Exception as e:
        logging.warning(f"Kursdaten-Abfrage für {symbol} fehlgeschlagen: {e}")
        return {'regular': None, 'currency': 'USD', 'change': None, 'changePercent': None, 'symbol': symbol}

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
        ticker = yf.Ticker(symbol)
        news = getattr(ticker, 'news', None) or []
        headlines = []
        for item in news:
            title = item.get('title')
            if not title:
                continue
            related = item.get('relatedTickers') or []
            if symbol in related:
                headlines.append(title)
        if len(headlines) < 5:
            for item in news:
                title = item.get('title')
                if title and title not in headlines:
                    headlines.append(title)
                if len(headlines) >= 5:
                    break
        return headlines[:20]
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
        summaries[ticker] = summary

    # 📁 Ergebnisse speichern
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    out_path = f"data/output/summaries/{ts}_ai_trendberichte.md"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        for ticker, summary in summaries.items():
            f.write(f"## {ticker}\n{summary}\n\n")

    print(f"\n✅ Zusammenfassungen gespeichert unter: {out_path}")

if __name__ == "__main__":
    main()
