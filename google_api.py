import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

SHEET_NAME = "Lista Presença QR"
cabecalho = ["Nome", "Matrícula", "Setor", "Data/Hora", "IP"]

scope = ["https://www.googleapis.com/auth/spreadsheets"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

if sheet.row_count == 0 or sheet.cell(1, 1).value != "Nome":
    sheet.insert_row(cabecalho, 1)


def registrar_presenca(nome, matricula, setor, ip):
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    registro = [nome, matricula, setor, timestamp, ip]
    sheet.append_row(registro)


def get_presencas():
    return sheet.get_all_values()
