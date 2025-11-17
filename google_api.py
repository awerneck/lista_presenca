import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

SHEET_NAME = "Lista Presença QR"
HEADERS = ["Nome", "Matrícula", "Setor", "Data/Hora", "IP"]

scope = ["https://www.googleapis.com/auth/spreadsheets"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

if sheet.row_count == 0 or sheet.cell(1, 1).value != "Nome":
    sheet.insert_row(HEADERS, 1)


def registrar_presenca(nome, matricula, setor, ip):
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    sheet.append_row([nome, matricula, setor, timestamp, ip])


def get_presencas():
    return sheet.get_all_values()


def ja_registrado_hoje(matricula):
    registros = sheet.get_all_values()

    for linha in registros[1:]:
        if linha[1] == matricula:
            data = datetime.strptime(linha[3], "%d/%m/%Y %H:%M:%S")
            if data.date() == datetime.now().date():
                return True
    return False
