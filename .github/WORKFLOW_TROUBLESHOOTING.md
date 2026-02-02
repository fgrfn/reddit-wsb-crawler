# Workflow Troubleshooting Guide

## Fehler: "Resource not accessible by integration"

Dieser Fehler tritt auf, wenn GitHub Actions nicht die erforderlichen Permissions hat.

### Lösung:

#### 1. Repository Settings überprüfen

Gehe zu: **Settings → Actions → General → Workflow permissions**

Stelle sicher, dass eine der folgenden Optionen aktiviert ist:
- ✅ **Read and write permissions** (empfohlen)
- ❌ **Read repository contents and packages permissions** (zu restriktiv)

#### 2. "Allow GitHub Actions to create and approve pull requests"
- ✅ Diese Option sollte aktiviert sein (optional, aber empfohlen)

### Schritte:

```
1. Öffne: https://github.com/fgrfn/reddit-wsb-crawler/settings/actions
2. Scrolle zu "Workflow permissions"
3. Wähle "Read and write permissions"
4. Klicke "Save"
5. Re-run den fehlgeschlagenen Workflow
```

### Alternative: Personal Access Token (PAT)

Falls die obige Lösung nicht funktioniert, erstelle einen PAT:

1. Gehe zu: https://github.com/settings/tokens
2. Klicke "Generate new token (classic)"
3. Gebe einen Namen: z.B. "WSB-Crawler Release Token"
4. Wähle Scopes:
   - ✅ `repo` (alle)
   - ✅ `write:packages`
   - ✅ `workflow`
5. Klicke "Generate token"
6. Kopiere den Token
7. Gehe zu: https://github.com/fgrfn/reddit-wsb-crawler/settings/secrets/actions
8. Klicke "New repository secret"
9. Name: `PAT_TOKEN`
10. Value: [eingefügter Token]
11. Klicke "Add secret"

Dann ändere im Workflow:

```yaml
- name: Checkout code
  uses: actions/checkout@v4
  with:
    token: ${{ secrets.PAT_TOKEN }}  # Statt GITHUB_TOKEN
```

## Weitere häufige Fehler:

### "git push" schlägt fehl
**Ursache:** Permissions oder Branch Protection
**Lösung:** 
- Deaktiviere Branch Protection für `github-actions[bot]`
- Oder: Verwende PAT statt GITHUB_TOKEN

### Docker Push schlägt fehl
**Ursache:** Package visibility oder Permissions
**Lösung:**
- Package Visibility auf "Public" setzen
- `packages: write` Permission prüfen

### Tag existiert bereits
**Ursache:** Release wurde nicht vollständig gelöscht
**Lösung:**
```bash
git push --delete origin v1.0.0
git tag -d v1.0.0
```

## Workflow manuell testen:

```bash
# Lokale Version erhöhen
echo "1.0.1" > version.txt
git add version.txt
git commit -m "test: manual version bump"
git push

# Workflow-Status prüfen
gh run list --workflow=release.yml

# Logs anzeigen
gh run view --log
```

## Debug-Modus aktivieren:

Füge am Anfang des Workflows hinzu:

```yaml
env:
  ACTIONS_STEP_DEBUG: true
  ACTIONS_RUNNER_DEBUG: true
```

## Nützliche GitHub CLI Befehle:

```bash
# Workflow-Runs anzeigen
gh run list

# Spezifischen Run anzeigen
gh run view [RUN_ID]

# Run erneut starten
gh run rerun [RUN_ID]

# Workflow manuell triggern
gh workflow run release.yml
```
