import os
import openai
import pickle
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict
import logging
from run_crawler_headless import get_yf_price  # Importiere die Funktion, falls nötig

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
    for sr_name, sr_data in result.get("subreddits", {}).items():
        for s, hits in sr_data["symbol_hits"].items():
            if s == ticker and hits >= 1:
                # Hier KEINE Subreddit- oder Nennungs-Infos mehr!
                texts.append("")  # oder: texts.append(f"{s}")
    return "\n".join([t for t in texts if t])

def summarize_ticker(ticker, context):
    print(f"📄 Sende {ticker}-Kontext an OpenAI ...")
    prompt = (
        f"Fasse die wichtigsten Erkenntnisse zum Aktienkürzel {ticker} zusammen:\n"
        f"{context}\n\n"
        f"Wenn keine Reddit-Diskussionen vorliegen, beziehe dich ausschließlich auf die Kursdaten und die aktuellen Nachrichten-Headlines. "
        f"Bitte beantworte folgende Punkte in 3–5 Sätzen:\n"
        f"- Gibt es relevante Nachrichten oder Kursbewegungen?\n"
        f"- Gibt es Hinweise auf Trends, Stimmungen oder besondere Ereignisse?\n"
        f"Vermeide jegliche Erwähnung von Subreddits, Nennungszahlen oder Reddit-Diskussionen, wenn keine konkreten Inhalte vorliegen. "
        f"Erfinde keine Reddit-Diskussionen, wenn keine im Kontext stehen."
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Du bist Warren Buffett, ein US-amerikanischer Investor, Unternehmer und Philanthrop – bekannt als einer der erfolgreichsten Anleger der Geschichte und analysiert die Stimmung der Reddit Community. Dein Ziel ist es, Trendaktien frühzeitig zu erkennen, um entsprechend vor einem 'Hype' oder 'Gamma Squeeze' zu kaufen und mit Gewinn zu verkaufen."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=500
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        logging.error(f"OpenAI-Fehler für {ticker}: {e}")
        return f"❌ Fehler für {ticker}: {e}"

def get_yf_news(symbol):
    import yfinance as yf
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news  # Gibt eine Liste von Dicts zurück
        # Filtere nur News mit Titel und (optional) passendem Symbol bzw. verwandten Tickers aus er selben Branche
        headlines = [item.get("title") for item in news if "title" in item and (item.get("relatedTickers") is None or symbol in item.get("relatedTickers", []))]
        return headlines[:5]  # z.B. die 5 aktuellsten Headlines
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
