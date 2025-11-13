import os
import json
import qrcode
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from datetime import datetime
from io import StringIO
from waitress import serve

# ============================================================
# CONFIGURAÇÃO BÁSICA DO FLASK
# ============================================================
app = Flask(__name__)
app.secret_key = "chave_secreta_segura"

# ============================================================
# CONFIGURAÇÃO DO GOOGLE SHEETS
# ============================================================
escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Carrega as credenciais diretamente da variável de ambiente do Render
credenciais_dict = json.loads(os.environ["GOOGLE_CREDS_JSON"])
credenciais = ServiceAccountCredentials.from_json_keyfile_dict(credenciais_dict, escopo)
cliente = gspread.authorize(credenciais)

# Abra a planilha (garanta que ela tenha as colunas: Nome Completo | Matrícula | Setor | Data/Hora)
planilha = cliente.open("Lista de Presença").sheet1

# ============================================================
# GERAÇÃO DO QR CODE COM LINK PÚBLICO DO RENDER
# ============================================================
def gerar_qrcode():
    # Substitua pelo seu domínio do Render após o primeiro deploy
    url = "https://lista-presenca-kdwr.onrender.com/presenca"
    img = qrcode.make(url)
    os.makedirs("static", exist_ok=True)
    img.save("static/qrcode.png")

# Gera QRCode na inicialização
gerar_qrcode()

# ============================================================
# ROTAS DO SISTEMA
# ============================================================

# Página inicial — mostra o QR Code
@app.route("/")
def index():
    return render_template("index.html", imagem_qrcode="static/qrcode.png")

# Página de presença — formulário preenchido pelo participante
@app.route("/presenca", methods=["GET", "POST"])
def presenca():
    if request.method == "POST":
        nome = request.form["nome"]
        matricula = request.form["matricula"]
        setor = request.form["setor"]
        datahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        planilha.append_row([nome, matricula, setor, datahora])
        return render_template("presenca.html", sucesso=True)
    return render_template("presenca.html", sucesso=False)

# Página de login do administrador
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]
        if usuario == "admin" and senha == "1234":
            session["usuario"] = usuario
            return redirect(url_for("admin"))
        else:
            return render_template("login.html", erro=True)
    return render_template("login.html", erro=False)

# Painel administrativo
@app.route("/admin")
def admin():
    if "usuario" not in session:
        return redirect(url_for("login"))

    registros = planilha.get_all_records()
    df = pd.DataFrame(registros)
    return render_template("admin.html", tabelas=[df.to_html(classes="table table-striped", index=False)], busca=False)

# Filtro de busca
@app.route("/buscar", methods=["POST"])
def buscar():
    if "usuario" not in session:
        return redirect(url_for("login"))

    nome_busca = request.form["nome"].lower().strip()
    data_busca = request.form["data"].strip()
    registros = planilha.get_all_records()
    df = pd.DataFrame(registros)

    if nome_busca:
        df = df[df["Nome Completo"].str.lower().str.contains(nome_busca)]
    if data_busca:
        df = df[df["Data/Hora"].str.startswith(data_busca)]

    return render_template("admin.html", tabelas=[df.to_html(classes="table table-striped", index=False)], busca=True)

# Logout
@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("index"))

# ============================================================
# EXECUÇÃO (LOCAL OU NO RENDER)
# ============================================================
if __name__ == "__main__":
     from waitress import serve
    serve(app, host="0.0.0.0", port=8080)
