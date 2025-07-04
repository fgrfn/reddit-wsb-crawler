import os
import pickle
import pandas as pd

PICKLE_DIR = "data/output/pickle"
EXCEL_OUT = "data/output/excel/crawler_results_detailed.xlsx"

def load_results():
    records = []
    for filename in sorted(os.listdir(PICKLE_DIR)):
        if filename.endswith(".pkl"):
            filepath = os.path.join(PICKLE_DIR, filename)
            try:
                with open(filepath, "rb") as f:
                    result = pickle.load(f)
                    run_id = result.get("run_id", "unknown")
                    for subreddit, srdata in result.get("subreddits", {}).items():
                        for ticker, count in srdata.get("symbol_hits", {}).items():
                            records.append({
                                "run_id": run_id,
                                "subreddit": subreddit,
                                "ticker": ticker,
                                "count": count,
                                "posts_checked": srdata.get("posts_checked", 0)
                            })
            except Exception as e:
                print(f"⚠️ Fehler beim Laden von {filename}: {e}")
    return records

def save_to_excel(records):
    df = pd.DataFrame(records)
    if df.empty:
        print("🚫 Keine Daten verfügbar.")
        return
    df = df.sort_values(["run_id", "subreddit", "count"], ascending=[True, True, False])
    os.makedirs(os.path.dirname(EXCEL_OUT), exist_ok=True)
    df.to_excel(EXCEL_OUT, index=False)
    print(f"✅ Excel-Datei gespeichert unter: {EXCEL_OUT}")

def main():
    print("📥 Lade Pickle-Ergebnisse aus Subreddits ...")
    data = load_results()
    print(f"📈 {len(data)} Einträge verarbeitet.")
    save_to_excel(data)

if __name__ == "__main__":
    main()