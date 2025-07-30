import os
import pickle

PICKLE_DIR = "data/output/pickle"

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

def main():
    print("📥 Lade Pickle-Ergebnisse aus Subreddits ...")
    data = load_results()
    print(f"📈 {len(data)} Einträge verarbeitet.")
    # Keine Excel- oder GSheet-Funktion mehr

if __name__ == "__main__":
    main()