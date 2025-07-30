from pathlib import Path
import os
import pickle
from collections import defaultdict
from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, RateLimitError
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

# 🔧 Projekt-Root ermitteln
BASE_DIR = Path(__file__).resolve().parent.parent
SUMMARY_DIR = BASE_DIR / "data" / "output" / "summaries"
os.makedirs(SUMMARY_DIR, exist_ok=True)

# 🔐 .env laden
load_dotenv(dotenv_path=BASE_DIR / "config" / ".env")

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("❌ Kein OpenAI API-Key gefunden. Bitte .env-Datei prüfen.")
    return OpenAI(api_key=api_key)

def get_market_trend(ticker):
    try:
        data = yf.Ticker(ticker).history(period="7d")
        if data.empty:
            return "Keine Kursdaten verfügbar"
        change = data["Close"].iloc[-1] - data["Close"].iloc[0]
        pct = (change / data["Close"].iloc[0]) * 100
        if pct > 5:
            return f"steigend (+{pct:.1f} %)"
        elif pct < -5:
            return f"fallend ({pct:.1f} %)"
        else:
            return f"seitwärts ({pct:.1f} %)"
    except Exception:
        return "Fehler beim Abrufen der Kursdaten"

def ask_openai_summary(ticker, context):
    client = get_openai_client()
    trend = get_market_trend(ticker)
    system = "Du bist ein Analyst, der Reddit-Diskussionen zu Aktien auswertet."
    prompt = (
        f"Fasse die wichtigsten Erkenntnisse zur Aktie {ticker} in maximal 3 Sätzen und höchstens 400 Zeichen zusammen:\n"
        f"{context}\n\n"
        f"- Wie hat sich der Kurs von {ticker} zuletzt entwickelt?\n"
        f"- Gibt es relevante Nachrichten zu {ticker}?\n"
        f"Falls keine Kursbewegung oder Nachrichten vorliegen, schreibe: 'Keine relevanten Kursbewegungen oder Nachrichten zu {ticker} im angegebenen Zeitraum.'"
        f"Nutze ausschließlich die im Kontext genannten Daten und Headlines zu {ticker}. Erfinde keine weiteren Inhalte."
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=250
    )
    return response.choices[0].message.content.strip()

def generate_summary(pickle_path, include_all=False, streamlit_out=None, only_symbols=None):
    with open(pickle_path, "rb") as f:
        result = pickle.load(f)

    run_id = result["run_id"]
    data = result.get("subreddits", {})
    combined_context = defaultdict(str)

    for sr, srdata in data.items():
        for sym, count in srdata.get("symbol_hits", {}).items():
            if only_symbols:
                if sym in only_symbols:
                    combined_context[sym] += f"{count} Nennungen in r/{sr}. "
            elif include_all or count > 5:
                combined_context[sym] += f"{count} Nennungen in r/{sr}. "

    if not combined_context:
        if streamlit_out:
            streamlit_out.warning("⚠️ Keine geeigneten Ticker für Zusammenfassung gefunden.")
        return {}

    summaries = {}
    success, failed = [], []
    total = len(combined_context)

    def get_summary(ticker, context):
        try:
            summary = ask_openai_summary(ticker, context)
            return ticker, summary, None
        except (APIConnectionError, RateLimitError, Exception) as e:
            return ticker, None, e

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(get_summary, ticker, context)
            for ticker, context in combined_context.items()
        ]
        for i, future in enumerate(as_completed(futures), 1):
            ticker, summary, error = future.result()
            if streamlit_out:
                streamlit_out.markdown(f"🔄 **[{i}/{total}]** ⏳ Verarbeite `{ticker}` ...")
            if summary:
                summaries[ticker] = summary
                success.append(ticker)
                if streamlit_out:
                    streamlit_out.success(f"✅ {ticker} abgeschlossen")
            else:
                failed.append(ticker)
                if streamlit_out:
                    streamlit_out.error(f"❌ Fehler bei {ticker}: {error}")

    md_lines = [f"# Reddit-KI-Zusammenfassung für {run_id}"]
    for ticker in sorted(summaries):
        md_lines.append(f"\n## {ticker}\n{summaries[ticker]}")

    md_path = SUMMARY_DIR / f"{run_id}_summary.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    if streamlit_out:
        if success:
            streamlit_out.markdown("### ✅ Erfolgreiche Zusammenfassungen")
            for t in success:
                streamlit_out.markdown(f"🟢 **{t}** – abgeschlossen")
        if failed:
            streamlit_out.markdown("### ❌ Fehlerhafte Zusammenfassungen")
            for t in failed:
                streamlit_out.markdown(f"🔴 **{t}** – fehlgeschlagen")
        streamlit_out.success(f"📝 Zusammenfassung gespeichert unter: `{md_path}`")

    return {"success": success, "failed": failed}
