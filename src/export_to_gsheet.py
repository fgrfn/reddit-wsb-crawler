import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

EXCEL_PATH = "data/output/excel/crawler_results_detailed.xlsx"
CREDENTIALS_PATH = "config/gsheets_credentials.json"
SHEET_NAME = "Reddit Crawler Ergebnis"
TAB_NAME = "Aktuelle Daten"

def export_excel_to_gsheet():
    # 🔐 Authentifiziere über Service Account
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_PATH, scope)
    client = gspread.authorize(creds)

    # 📄 Öffne Google Sheet
    try:
        sheet = client.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        print(f"❌ Google Sheet '{SHEET_NAME}' nicht gefunden.")
        return

    # 📊 Lade Excel in DataFrame
    df = pd.read_excel(EXCEL_PATH)

    # 🧽 Bestehendes Tab löschen (optional)
    try:
        worksheet = sheet.worksheet(TAB_NAME)
        sheet.del_worksheet(worksheet)
    except:
        pass  # Tab existiert noch nicht

    # ➕ Neues Tab erstellen
    worksheet = sheet.add_worksheet(title=TAB_NAME, rows=str(len(df)+10), cols="20")
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())

    print(f"✅ Daten in Google Sheet hochgeladen ➜ Tab: {TAB_NAME}")

if __name__ == "__main__":
    export_excel_to_gsheet()
