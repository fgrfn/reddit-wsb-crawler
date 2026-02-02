# 🔐 Personal Access Token (PAT) Setup

## Warum PAT statt GITHUB_TOKEN?

`GITHUB_TOKEN` wird automatisch von GitHub Actions bereitgestellt, hat aber **eingeschränkte Rechte**:
- ❌ Kann keine Releases erstellen (bei einigen Repo-Konfigurationen)
- ❌ Kann Branch Protection Rules nicht umgehen
- ❌ Kann keine Workflows triggern
- ❌ Limitierte Package-Rechte

Ein **Personal Access Token (PAT)** hat **volle Rechte** und löst diese Probleme.

---

## 📝 PAT erstellen (2 Minuten)

### Schritt 1: Token generieren

1. Öffne: https://github.com/settings/tokens
2. Klicke: **"Generate new token"** → **"Generate new token (classic)"**
3. **Name:** `WSB-Crawler-Release-Token`
4. **Expiration:** `No expiration` (oder 1 Jahr)
5. **Scopes auswählen:**
   ```
   ✅ repo (alle darunter)
      ✅ repo:status
      ✅ repo_deployment
      ✅ public_repo
      ✅ repo:invite
      ✅ security_events
   
   ✅ write:packages
      ✅ read:packages
   
   ✅ workflow
   ```

6. Klicke: **"Generate token"**
7. **⚠️ WICHTIG:** Kopiere den Token **sofort** (wird nur einmal angezeigt!)

### Schritt 2: Token als Secret speichern

1. Öffne: https://github.com/fgrfn/reddit-wsb-crawler/settings/secrets/actions
2. Klicke: **"New repository secret"**
3. **Name:** `PAT_TOKEN` (genau so!)
4. **Value:** [Füge den kopierten Token ein]
5. Klicke: **"Add secret"**

---

## ✅ Fertig!

Der Workflow verwendet jetzt automatisch `PAT_TOKEN` falls vorhanden, sonst `GITHUB_TOKEN`:

```yaml
token: ${{ secrets.PAT_TOKEN || secrets.GITHUB_TOKEN }}
```

### Workflow erneut starten:

1. Gehe zu: https://github.com/fgrfn/reddit-wsb-crawler/actions
2. Wähle den fehlgeschlagenen Run
3. Klicke: **"Re-run all jobs"**

---

## 🔒 Sicherheit

- ✅ Token ist verschlüsselt gespeichert
- ✅ Nur in GitHub Actions sichtbar
- ✅ Kann jederzeit widerrufen werden: https://github.com/settings/tokens
- ✅ Bei Kompromittierung: Token löschen und neu erstellen

---

## 🧪 Token testen

```bash
# Teste den Token lokal (optional)
export GITHUB_TOKEN="dein_pat_token"

# Teste API-Zugriff
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/fgrfn/reddit-wsb-crawler

# Sollte Repo-Infos zurückgeben, nicht 401/403
```

---

## ❓ FAQ

### Muss ich das wirklich machen?

**Ja**, wenn der Fehler `"Resource not accessible by integration"` auftritt.

Alternative: Repository Settings → Actions → "Read and write permissions" aktivieren
(Funktioniert nicht immer bei Organization Repos oder mit Branch Protection)

### Ist das sicher?

**Ja**, solange du:
- ✅ Token nicht in Code einfügst
- ✅ Token als Secret speicherst
- ✅ Minimal nötige Scopes wählst
- ✅ Expiration setzt (empfohlen)

### Was wenn der Token abläuft?

Workflow schlägt fehl → Neuen Token generieren → Secret aktualisieren

### Kann ich Fine-grained PAT verwenden?

**Ja**, aber Classic Token ist einfacher:

Fine-grained PAT Scopes:
- `Contents: Read and write`
- `Metadata: Read-only`
- `Workflows: Read and write`

---

## 🆘 Immer noch Probleme?

Siehe [WORKFLOW_TROUBLESHOOTING.md](WORKFLOW_TROUBLESHOOTING.md)
