import os
import json
import qrcode
import requests
import pytz
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from waitress import serve

# ============================================================
# CONFIGURAÇÕES DO FLASK
# ============================================================
app = Flask(__name__)
app.secret_key = "chave_secreta_segura"

# ============================================================
# CONFIGURAÇÃO DA API DO GOOGLE SHEETS
# ============================================================
escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credenciais_dict = json.loads(os.environ["GOOGLE_CREDS_JSON"])
credenciais = ServiceAccountCredentials.from_json_keyfile_dict(credenciais_dict, escopo)
cliente = gspread.authorize(credenciais)

# Aba 1 da planilha "Lista de Presença"
sheet = cliente.open("Lista de Presença").sheet1

# ============================================================
# GERAÇÃO DO QR CODE
# ============================================================
def gerar_qrcode():
    url = "https://lista-presenca-kdwr.onrender.com/presenca"
    img = qrcode.make(url)
    os.makedirs("static", exist_ok=True)
    img.save("static/qrcode.png")

gerar_qrcode()

# ============================================================
# ROTAS
# ============================================================
@app.route("/")
def index():
    return render_template("index.html", imagem_qrcode="static/qrcode.png")


@app.route("/presenca", methods=["GET", "POST"])
def presenca():
    if request.method == "POST":
        nome = request.form.get("nome")
        matricula = request.form.get("matricula")
        setor = request.form.get("setor")

        # Data e hora correta do Brasil
        fuso = pytz.timezone("America/Sao_Paulo")
        datahora = datetime.now(fuso)
        datahora_str = datahora.strftime("%d/%m/%Y %H:%M:%S")
        dia_hoje = datahora.strftime("%d/%m/%Y")

        # IP do dispositivo
        ip = request.remote_addr

        # Busca localização aproximada via IP
        cidade = "Desconhecida"
        estado = "Desconhecido"
        pais = "Desconhecido"

        try:
            geo = requests.get(f"https://ipapi.co/{ip}/json/").json()
            cidade = geo.get("city", "Desconhecida")
            estado = geo.get("region", "Desconhecido")
            pais = geo.get("country_name", "Desconhecido")
        except:
            pass

        cidade_estado = f"{cidade}/{estado}"

        # Bloqueio de presença duplicada no mesmo dia pela matrícula
        registros = sheet.get_all_records()
        for r in registros:
            if str(r["Matrícula"]) == str(matricula) and r["Data/Hora"].startswith(dia_hoje):
                return render_template("presenca.html",
                                       erro_duplicado=True,
                                       nome=nome,
                                       hora=datahora_str)

        # Grava na planilha na ordem definida
        sheet.append_row([nome, matricula, setor, datahora_str, ip, cidade_estado, pais])

        return render_template("presenca.html",
                               confirmacao=True,
                               nome=nome,
                               hora=datahora_str)

    return render_template("presenca.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        if usuario == "admin" and senha == "1234":
            session["usuario"] = usuario
            return redirect(url_for("admin"))
        return render_template("login.html", erro=True)

    return render_template("login.html")


@app.route("/admin")
def admin():
    if "usuario" not in session:
        return redirect(url_for("login"))

    registros = sheet.get_all_records()
    return render_template("admin.html", registros=registros)


@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("index"))


# ============================================================
# EXECUÇÃO
# ============================================================
if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)
