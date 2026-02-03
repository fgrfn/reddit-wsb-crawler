# Discord Rich Embeds

## Übersicht

Ab Version 1.4.2 verwendet der WSB-Crawler **Discord Rich Embeds** für visuell ansprechendere Nachrichten mit:

- 🎨 **Farbcodierung** - Status auf einen Blick erkennbar
- 📊 **Strukturierte Felder** - Bessere Lesbarkeit durch Formatierung
- 🔗 **Klickbare Links** - Direkter Zugriff auf Yahoo Finance
- ⏱️ **Timestamps** - Automatische Zeitstempel in Discord

## Beispiele

### Status-Nachricht (Heartbeat)

**Vorher (Text):**
```
🟢 **WSB-Crawler Status**
🕐 Letzter Crawl: 03.02.2026 14:30:00 (vor 5 Minuten)
📊 Posts überprüft: 1337
🔔 Alerts ausgelöst: 2
⏭️ Nächster Crawl: 03.02.2026 15:00:00

**Top 5 Erwähnungen:**
1. TSLA: 42
2. GME: 38
3. AAPL: 25
```

**Nachher (Rich Embed):**
- Farbige Sidebar (🟢 Grün = aktiv, 🟡 Gelb = veraltet, 🔴 Rot = Fehler)
- Strukturierte Felder für bessere Übersicht
- Timestamp im Discord-Format
- Professionelleres Erscheinungsbild

### Alert-Nachricht

**Vorher (Text):**
```
⚠️ WSB-ALARM — Ungewöhnliche Aktivität entdeckt
💾 hits_030226_143000.pkl
⏰ 03.02.2026 14:30:00

🥇 TSLA - Tesla Inc. 🚨
🔢 Nennungen: 42 (Δ +12)
💵 245.67 USD (+12.34 USD, +5.28%) 📈 [03.02.2026 14:25] | 🌅 Pre-Market: 243.50 USD | Trends: 1h ▲ +1.2% · 24h ▲ +5.28% · 7d ▼ -2.3% | https://finance.yahoo.com/quote/TSLA
🧠 Tesla entwickelt Elektrofahrzeuge und Energiespeicherlösungen...
📰 Tesla kündigt neue Gigafactory in Deutschland an
```

**Nachher (Rich Embed):**
- Orange Sidebar für Alerts (Signalfarbe)
- Klar strukturierte Felder pro Ticker
- Kurs-Informationen mit Emojis
- Klickbare Yahoo Finance Links
- News-Headlines eingebettet
- Kompaktere Darstellung bei gleichem Informationsgehalt

## Farbcodierung

### Status-Nachrichten
| Status | Farbe | Hex-Code | Bedeutung |
|--------|-------|----------|-----------|
| 🟢 Aktiv | Grün | `#00ff00` | Letzter Crawl < 30 Min |
| 🟡 Veraltet | Gelb | `#ffff00` | Letzter Crawl 30 Min - 6 Std |
| 🔴 Fehler | Rot | `#ff0000` | Letzter Crawl > 6 Std |

### Alert-Nachrichten
| Typ | Farbe | Hex-Code | Bedeutung |
|-----|-------|----------|-----------|
| ⚠️ Alert | Orange | `#ff6b00` | Ungewöhnliche Aktivität |

## Konfiguration

### Embeds aktivieren/deaktivieren

Die Embed-Funktionalität ist standardmäßig aktiviert. Zum Deaktivieren:

```python
# In run_crawler_headless.py oder eigenen Scripts
status_msg = format_heartbeat_message(..., use_embed=False)
alert_msg = format_discord_message(..., use_embed=False)
```

### Umgebungsvariablen

Keine neuen Umgebungsvariablen erforderlich. Bestehende Konfiguration funktioniert weiter:

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_STATUS_UPDATE=true  # Heartbeat-Updates aktivieren
```

## Migration

### Bestehende Installationen

✅ **Keine Änderungen erforderlich!**

- Embeds werden automatisch verwendet
- Bestehende Text-Nachrichten werden zu Embeds konvertiert
- Fallback auf Text-Format bei Problemen
- Webhook-URLs bleiben unverändert

### Status-Nachrichten editieren

Bestehende Status-Nachrichten (Text) können problemlos zu Embeds editiert werden:

```python
# Alter Text wird durch Embed ersetzt
send_or_edit_discord_message("", message_id="123456", embed=new_embed)
```

## Testen

Test-Script ausführen:

```bash
# Voraussetzung: DISCORD_WEBHOOK_URL in config/.env gesetzt
cd /workspaces/reddit-wsb-crawler
python src/test_discord_embeds.py
```

Das Script sendet drei Test-Nachrichten:
1. **Heartbeat Embed** - Status-Nachricht mit Rich Embed
2. **Alert Embed** - Alarm-Nachricht mit Ticker-Details
3. **Text Fallback** - Text-Version zum Vergleich

## Vorteile

### Für Nutzer
- ✅ Bessere Lesbarkeit auf mobilen Geräten
- ✅ Schnellere Erfassung wichtiger Informationen
- ✅ Professionelleres Erscheinungsbild
- ✅ Statusfarben sofort erkennbar

### Technisch
- ✅ Weniger Zeichenverbrauch (kein Markdown-Overhead)
- ✅ Strukturierte Daten statt Text-Parsing
- ✅ Konsistente Formatierung
- ✅ Abwärtskompatibel (Fallback auf Text)

## Einschränkungen

- Discord Embeds haben ein Limit von **6000 Zeichen** (Text: 2000)
- Maximal **25 Felder** pro Embed
- **10 Embeds** pro Nachricht möglich
- Webhooks können keine Embeds mit Thumbnails/Images direkt hochladen (nur URLs)

## Technische Details

### Embed-Struktur

```python
{
    "title": "⚠️ WSB-ALARM",
    "description": "📅 03.02.2026 14:30:00",
    "color": 0xff6b00,  # Orange (Dezimal)
    "fields": [
        {
            "name": "🥇 TSLA — Tesla Inc. 🚨",
            "value": "🔢 **42** Nennungen (Δ **+12**)\n...",
            "inline": False
        }
    ],
    "footer": {
        "text": "💾 hits_030226_143000.pkl"
    },
    "timestamp": "2026-02-03T14:30:00.000Z"  # ISO 8601
}
```

### Discord API Endpoint

```
POST https://discord.com/api/webhooks/{webhook.id}/{webhook.token}?wait=true
Content-Type: application/json

{
    "embeds": [
        { ... }
    ]
}
```

## Weitere Informationen

- [Discord Webhook API](https://discord.com/developers/docs/resources/webhook)
- [Discord Embed Limits](https://discord.com/developers/docs/resources/channel#embed-limits)
- [Discord Embed Visualizer](https://leovoel.github.io/embed-visualizer/)

## Changelog

### v1.4.2 - 2026-02-03
- ✨ Discord Rich Embeds für Status- und Alert-Nachrichten
- 🎨 Farbcodierung für Status (Grün/Gelb/Rot)
- 📊 Strukturierte Felder für bessere Lesbarkeit
- 🔗 Klickbare Yahoo Finance Links
- ⏱️ Automatische Discord-Timestamps
- ✅ Abwärtskompatibel mit Text-Format
