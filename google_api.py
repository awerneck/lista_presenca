# google_api.py
import os, json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

SHEET_NAME = os.environ.get("SHEET_NAME", "Lista de Presença")
HEADERS = ["Nome", "Matrícula", "Setor", "Data/Hora", "IP"]

GCP_JSON = os.environ.get("GOOGLE_CREDS_JSON")
SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

client = None
sheet = None

if GCP_JSON:
    creds_dict = json.loads(GCP_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    # ensure headers
    try:
        first = sheet.row_values(1)
        if not first or first[0] != "Nome":
            sheet.insert_row(HEADERS, 1)
    except Exception:
        pass

def append_row(row):
    if not sheet: return
    sheet.append_row(row)

def get_all():
    if not sheet: return []
    return sheet.get_all_values()

def get_all_records():
    if not sheet: return []
    return sheet.get_all_records()

def ja_registrado_hoje(matricula):
    if not sheet: return False
    records = sheet.get_all_records()
    hoje = datetime.now().strftime("%d/%m/%Y")
    for r in records:
        if str(r.get("Matrícula","")) == str(matricula):
            dt = str(r.get("Data/Hora",""))
            if dt:
                if dt.split(" ")[0] == hoje:
                    return True
    return False
