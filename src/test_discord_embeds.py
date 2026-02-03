#!/usr/bin/env python
"""
Test-Script für Discord Rich Embeds.

Sendet Beispiel-Nachrichten um die visuellen Verbesserungen zu demonstrieren.
"""

import os
import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from discord_utils import send_discord_notification, format_heartbeat_message, format_discord_message
import pandas as pd
from datetime import datetime

def test_heartbeat_embed():
    """Testet die Heartbeat/Status-Nachricht mit Embed."""
    print("📤 Sende Heartbeat-Nachricht (Embed)...")
    
    top_tickers = [
        ("TSLA", 42),
        ("GME", 38),
        ("AAPL", 25),
        ("NVDA", 19),
        ("AMD", 15)
    ]
    
    timestamp = time.strftime("%d.%m.%Y %H:%M:%S")
    
    # Mit Embed (Standard)
    embed = format_heartbeat_message(
        timestamp=timestamp,
        run_id="test-123456",
        total_posts=1337,
        top_tickers=top_tickers,
        next_crawl_time="03.02.2026 15:30:00",
        triggered_count=2,
        use_embed=True
    )
    
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("❌ DISCORD_WEBHOOK_URL nicht gesetzt!")
        return False
    
    success = send_discord_notification("", embed=embed, webhook_url=webhook_url)
    
    if success:
        print("✅ Heartbeat-Embed erfolgreich gesendet!")
    else:
        print("❌ Fehler beim Senden")
    
    return success

def test_alert_embed():
    """Testet die Alert-Nachricht mit Embed."""
    print("\n📤 Sende Alert-Nachricht (Embed)...")
    
    timestamp = time.strftime("%d.%m.%Y %H:%M:%S")
    
    # Beispiel-Daten
    df_ticker = pd.DataFrame([
        {
            "Ticker": "TSLA",
            "Unternehmen": "Tesla Inc.",
            "Nennungen": 42,
            "Kurs": {
                "regular": 245.67,
                "currency": "USD",
                "change": 12.34,
                "changePercent": 5.28,
                "pre": 243.50,
                "post": None,
                "symbol": "TSLA",
                "timestamp": time.time(),
                "change_1h": 1.2,
                "change_24h": 5.28,
                "change_7d": -2.3,
                "market_state": "REGULAR"
            }
        },
        {
            "Ticker": "GME",
            "Unternehmen": "GameStop Corp.",
            "Nennungen": 38,
            "Kurs": {
                "regular": 18.92,
                "currency": "USD",
                "change": -0.45,
                "changePercent": -2.32,
                "pre": None,
                "post": 18.75,
                "symbol": "GME",
                "timestamp": time.time(),
                "change_1h": -0.5,
                "change_24h": -2.32,
                "change_7d": 8.7,
                "market_state": "POST"
            }
        }
    ])
    
    prev_nennungen = {"TSLA": 30, "GME": 33}
    name_map = {"TSLA": "Tesla Inc.", "GME": "GameStop Corp."}
    summary_dict = {
        "TSLA": {
            "summary": "Tesla entwickelt Elektrofahrzeuge und Energiespeicherlösungen. Das Unternehmen ist führend in der E-Mobilität.",
            "news": [
                {
                    "title": "Tesla kündigt neue Gigafactory in Deutschland an",
                    "source": "Reuters",
                    "url": "https://example.com/news1"
                }
            ]
        },
        "GME": {
            "summary": "GameStop ist ein Einzelhändler für Videospiele und Unterhaltungselektronik.",
            "news": []
        }
    }
    
    # Mit Embed (Standard)
    embed = format_discord_message(
        pickle_name="test_payload.pkl",
        timestamp=timestamp,
        df_ticker=df_ticker,
        prev_nennungen=prev_nennungen,
        name_map=name_map,
        summary_dict=summary_dict,
        next_crawl_time="03.02.2026 15:30:00",
        use_embed=True
    )
    
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("❌ DISCORD_WEBHOOK_URL nicht gesetzt!")
        return False
    
    success = send_discord_notification("", embed=embed, webhook_url=webhook_url)
    
    if success:
        print("✅ Alert-Embed erfolgreich gesendet!")
    else:
        print("❌ Fehler beim Senden")
    
    return success

def test_text_fallback():
    """Testet die Text-Fallback-Version (ohne Embed)."""
    print("\n📤 Sende Heartbeat-Nachricht (Text-Fallback)...")
    
    top_tickers = [("TSLA", 42), ("GME", 38), ("AAPL", 25)]
    timestamp = time.strftime("%d.%m.%Y %H:%M:%S")
    
    # Ohne Embed
    text = format_heartbeat_message(
        timestamp=timestamp,
        run_id="test-fallback",
        total_posts=1000,
        top_tickers=top_tickers,
        next_crawl_time="03.02.2026 15:30:00",
        triggered_count=1,
        use_embed=False
    )
    
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("❌ DISCORD_WEBHOOK_URL nicht gesetzt!")
        return False
    
    success = send_discord_notification(text, webhook_url=webhook_url)
    
    if success:
        print("✅ Text-Fallback erfolgreich gesendet!")
    else:
        print("❌ Fehler beim Senden")
    
    return success

if __name__ == "__main__":
    print("🧪 Discord Embed Test-Suite\n")
    print("=" * 50)
    
    # Lade .env wenn vorhanden
    env_path = Path(__file__).parent.parent / "config" / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        print(f"✅ .env geladen: {env_path}\n")
    else:
        print(f"⚠️  .env nicht gefunden: {env_path}")
        print("Stelle sicher, dass DISCORD_WEBHOOK_URL gesetzt ist!\n")
    
    # Tests ausführen
    results = []
    
    results.append(("Heartbeat Embed", test_heartbeat_embed()))
    time.sleep(2)  # Rate-Limiting vermeiden
    
    results.append(("Alert Embed", test_alert_embed()))
    time.sleep(2)
    
    results.append(("Text Fallback", test_text_fallback()))
    
    # Zusammenfassung
    print("\n" + "=" * 50)
    print("📊 Test-Ergebnisse:")
    print("=" * 50)
    for name, success in results:
        status = "✅ BESTANDEN" if success else "❌ FEHLER"
        print(f"{status} - {name}")
    
    success_count = sum(1 for _, s in results if s)
    print(f"\n{success_count}/{len(results)} Tests bestanden")
