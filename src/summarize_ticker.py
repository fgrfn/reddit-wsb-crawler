import os
import openai
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
    for sr_name, sr_data in result.get("subreddits", {}).items():
        for s, hits in sr_data["symbol_hits"].items():
            if s == ticker and hits >= 1:
                texts.append(f"[{sr_name}] {s} wurde {hits}× erwähnt.")
    return "\n".join(texts)

def summarize_ticker(ticker, context):
    print(f"📄 Sende {ticker}-Kontext an OpenAI ...")
    prompt = (
        f"Fasse die wichtigsten Erkenntnisse aus Reddit-Diskussionen zum Aktienkürzel {ticker} zusammen:\n"
        f"{context}\n\n"
        f"Bitte beantworte folgende Punkte in 3–5 Sätzen:\n"
        f"- Wie ist die allgemeine Stimmung (positiv, negativ, gemischt)?\n"
        f"- Welche konkreten Gründe, Argumente oder Trends werden genannt?\n"
        f"- Gibt es besondere Ereignisse, Nachrichten oder Meinungen, die häufig erwähnt werden?\n"
        f"Formuliere sachlich, kompakt und ohne Wiederholungen. "
        f"Beziehe dich auf den aktuellen Börsenkurs und relevante Börsennachrichten, falls vorhanden. "
        f"Verwende ausschließlich wahre und aktuelle Fakten, keine erfundenen, fiktiven oder hypothetischen Inhalte. "
        f"Erwähne NICHT, wie oft oder in welchen Subreddits der Ticker genannt wurde. "
        f"Verzichte auf Sätze wie 'Der Ticker wurde X-mal erwähnt' oder 'In r/wallstreetbets wurde Y-mal darüber gesprochen'."
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

def main():
    load_env()
    result, filename = load_latest_pickle()
    print(f"📥 Verarbeite: {filename}")

    relevant = result.get("relevant", {})
    summaries = {}

    for ticker, count in relevant.items():
        if count < 10:
            continue  # nur „diskussionsreiche“ Ticker
        text_block = extract_text(result, ticker)
        if text_block:
            summary = summarize_ticker(ticker, text_block)
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
