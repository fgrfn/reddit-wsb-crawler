import openai
import os
import pickle
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict
import logging

PRICING_URL = "https://platform.openai.com/pricing"
_warned_prices = False

openai.api_key = None

def _get_rate(var_name: str):
    val = os.getenv(var_name)
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except ValueError:
        logging.warning(f"Ungültiger Preis in {var_name} – bitte Zahl (USD pro 1k Tokens) setzen.")
        return None

def _get_gpt5_mini_rates():
    """
    Liest Preise (USD/1k Tokens) für gpt-5-mini aus .env:
      OPENAI_PRICE_IN_GPT5_MINI
      OPENAI_PRICE_OUT_GPT5_MINI
    """
    in_rate = _get_rate("OPENAI_PRICE_IN_GPT5_MINI")
    out_rate = _get_rate("OPENAI_PRICE_OUT_GPT5_MINI")
    return in_rate, out_rate

def _calc_cost(input_tokens: int, output_tokens: int, in_rate, out_rate):
    if in_rate is None or out_rate is None:
        return None
    return (input_tokens / 1000.0 * in_rate) + (output_tokens / 1000.0 * out_rate)

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
    for sr_name, sr_data in result.get("subreddits", {}).items():
        for s, hits in sr_data["symbol_hits"].items():
            if s == ticker and hits >= 1:
                # Hier KEINE Subreddit- oder Nennungs-Infos mehr!
                texts.append("")  # oder: texts.append(f"{s}")
    return "\n".join([t for t in texts if t])

def summarize_ticker(ticker, context):
    print(f"📄 Sende {ticker}-Kontext an OpenAI ...")
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
        response = openai.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            # temperature=0.0,  # ← entfernen, gpt-5-mini unterstützt nur Default
            max_completion_tokens=250
        )
        summary = response.choices[0].message.content.strip()

        # Tokens
        usage = getattr(response, "usage", None)
        input_tokens = 0
        output_tokens = 0
        if usage:
            # gpt-5-mini: input_tokens/output_tokens; ältere: prompt_tokens/completion_tokens
            input_tokens = getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0))
            output_tokens = getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0))

        # Preise für gpt-5-mini aus .env (kein Fallback auf Platzhalter)
        in_rate, out_rate = _get_gpt5_mini_rates()
        cost = _calc_cost(input_tokens, output_tokens, in_rate, out_rate)

        # Hinweis einmalig ausgeben, wenn Preise fehlen
        global _warned_prices
        if (in_rate is None or out_rate is None) and not _warned_prices:
            logging.warning(
                "Preise für gpt-5-mini nicht konfiguriert. Setze OPENAI_PRICE_IN_GPT5_MINI und "
                "OPENAI_PRICE_OUT_GPT5_MINI in config/.env (USD pro 1k Tokens). "
                f"Siehe {PRICING_URL}"
            )
            _warned_prices = True

        # Logging
        os.makedirs("logs", exist_ok=True)
        if cost is not None:
            logging.info(f"OpenAI-Kosten für {ticker}: {cost:.4f} USD (Input: {input_tokens}, Output: {output_tokens}, Modell: gpt-5-mini)")
        else:
            logging.info(f"OpenAI-Kosten für {ticker}: n/a (Preise nicht gesetzt) – Tokens: in={input_tokens}, out={output_tokens}, Modell: gpt-5-mini")

        cost_str = f"{cost:.4f}" if cost is not None else "NA"
        log_entry = f"{datetime.now().isoformat()},COST,{cost_str},TOKENS,{input_tokens},{output_tokens},{ticker},gpt-5-mini\n"

        for log_path in ["logs/openai_costs.log", "logs/openai_costs_crawl.log", "logs/openai_costs_day.log", "logs/openai_costs_total.log"]:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(log_entry)

        if not summary:
            summary = f"Keine relevanten Kursbewegungen oder Nachrichten zu {ticker} im angegebenen Zeitraum."
        return summary[:400]
    except Exception as e:
        logging.error(f"OpenAI-Fehler für {ticker}: {e}")
        return f"❌ Fehler für {ticker}: {e}"

def get_yf_price(symbol):
    import yfinance as yf
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price_data = {
            "regular": info.get("regularMarketPrice", "unbekannt"),
            "currency": info.get("currency", "USD"),
            "change": info.get("regularMarketChange", "unbekannt"),
            "changePercent": info.get("regularMarketChangePercent", "unbekannt")
        }
        return price_data
    except Exception as e:
        print(f"Kursdaten-Abfrage für {symbol} fehlgeschlagen: {e}")
        return {
            "regular": "unbekannt",
            "currency": "USD",
            "change": "unbekannt",
            "changePercent": "unbekannt"
        }

def get_yf_news(symbol):
    import yfinance as yf
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        # Nur News, bei denen der Ticker explizit in relatedTickers steht
        headlines = [
            item.get("title") for item in news
            if "title" in item and symbol in item.get("relatedTickers", [])
        ]
        # Falls zu wenig Treffer, ergänze allgemeine News
        if len(headlines) < 5:
            extra = [item.get("title") for item in news if "title" in item and item.get("title") not in headlines]
            headlines.extend(extra[:5 - len(headlines)])
        return headlines[:20]  # z.B. bis zu 20 Headlines
    except Exception as e:
        print(f"News-Abfrage für {symbol} fehlgeschlagen: {e}")
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
