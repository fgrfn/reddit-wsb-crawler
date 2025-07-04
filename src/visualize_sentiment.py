import os
import re
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import pandas as pd

SUMMARY_DIR = "data/output/summaries"
SHEET_OUT = "data/output/excel/ticker_sentiment_summary.xlsx"
CHART_DIR = "data/output/charts"

def parse_sentiment(text):
    text = text.lower()
    if "bearish" in text or "negativ" in text:
        return -1
    elif "bullish" in text or "positiv" in text:
        return 1
    elif "gemischt" in text or "mixed" in text:
        return 0
    else:
        return 0  # neutral fallback

def load_latest_summary():
    files = sorted(os.listdir(SUMMARY_DIR), reverse=True)
    for f in files:
        if f.endswith(".md"):
            with open(os.path.join(SUMMARY_DIR, f), "r", encoding="utf-8") as file:
                return file.read(), f
    raise FileNotFoundError("Keine Zusammenfassung gefunden.")

def extract_ticker_blocks(text):
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]
    results = []
    for block in blocks:
        lines = block.strip().split("\n", 1)
        if len(lines) == 2:
            ticker = lines[0].strip()
            summary = lines[1].strip()
            score = parse_sentiment(summary)
            results.append((ticker, summary, score))
    return results

def plot_bar_chart(results):
    os.makedirs(CHART_DIR, exist_ok=True)
    tickers = [t for t, _, _ in results]
    scores = [s for _, _, s in results]
    colors = ["green" if s > 0 else "red" if s < 0 else "gray" for s in scores]

    plt.figure(figsize=(10, 5))
    plt.bar(tickers, scores, color=colors)
    plt.axhline(0, color='black', linewidth=0.8)
    plt.title("📊 Sentiment pro Ticker")
    plt.ylabel("Stimmung (–1=bearish, 0=neutral, +1=bullish)")
    plt.tight_layout()
    out_path = os.path.join(CHART_DIR, "sentiment_bar_chart.png")
    plt.savefig(out_path)
    print(f"✅ Balkendiagramm gespeichert: {out_path}")
    plt.close()

def generate_wordclouds(results):
    for ticker, summary, _ in results:
        words = re.sub(r"[^\w\s]", "", summary)
        wordcloud = WordCloud(width=400, height=200, background_color="white").generate(words)
        out_path = os.path.join(CHART_DIR, f"{ticker}_wordcloud.png")
        wordcloud.to_file(out_path)
        print(f"☁️ Wordcloud für {ticker} gespeichert: {out_path}")

def export_to_excel(results):
    df = pd.DataFrame(results, columns=["Ticker", "Zusammenfassung", "Sentiment"])
    os.makedirs(os.path.dirname(SHEET_OUT), exist_ok=True)
    df.to_excel(SHEET_OUT, index=False)
    print(f"📄 Excel-Export gespeichert: {SHEET_OUT}")

def main():
    text, fname = load_latest_summary()
    print(f"📥 Lade Zusammenfassungen aus: {fname}")
    results = extract_ticker_blocks(text)
    if not results:
        print("🚫 Keine Ticker gefunden.")
        return
    plot_bar_chart(results)
    generate_wordclouds(results)
    export_to_excel(results)

if __name__ == "__main__":
    main()
