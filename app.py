import os
import json
import qrcode
import secrets
import requests
import pandas as pd
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for, session,
    jsonify, send_file, make_response
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
from waitress import serve

# ----------------------
# CONFIG
# ----------------------
TOKEN_TTL_SECONDS = int(os.environ.get("TOKEN_TTL_SECONDS", "300"))  # 5 min
QR_FILENAME = "static/qrcode.png"
SHEET_NAME = os.environ.get("SHEET_NAME", "Lista de Presença")  # se desejar alterar via env

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "chave_secreta_segura")

# ----------------------
# GOOGLE SHEETS AUTH
# ----------------------
escopo = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
credenciais_dict = json.loads(os.environ["GOOGLE_CREDS_JSON"])
credenciais = ServiceAccountCredentials.from_json_keyfile_dict(credenciais_dict, escopo)
cliente = gspread.authorize(credenciais)
planilha = cliente.open(SHEET_NAME).sheet1

# ----------------------
# TOKENS DINÂMICOS (em memória)
# ----------------------
# Estrutura: { token: expiry_datetime }
valid_tokens = {}

def gerar_token():
    token = secrets.token_urlsafe(16)
    valid_tokens[token] = datetime.utcnow() + timedelta(seconds=TOKEN_TTL_SECONDS)
    return token

def token_valido(token):
    if not token:
        return False
    exp = valid_tokens.get(token)
    if not exp:
        return False
    if datetime.utcnow() > exp:
        del valid_tokens[token]
        return False
    return True

def limpar_tokens_expirados():
    agora = datetime.utcnow()
    expired = [t for t, e in valid_tokens.items() if e < agora]
    for t in expired:
        del valid_tokens[t]

# ----------------------
# QR CODE (gera QR com token temporário)
# ----------------------
def gerar_qrcode_publico():
    limpar_tokens_expirados()
    token = gerar_token()
    url = f"{request_host()}/presenca?token={token}"
    img = qrcode.make(url)
    os.makedirs("static", exist_ok=True)
    img.save(QR_FILENAME)
    return token

def request_host():
    # tenta obter host público corretamente (quando chamado em contexto de request)
    host = os.environ.get("PUBLIC_URL")
    if host:
        return host.rstrip("/")
    # fallback para headers (usado nas requisições normais)
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host_hdr = request.headers.get("Host", request.host)
    return f"{proto}://{host_hdr}".rstrip("/")

# ----------------------
# UTIL: obter IP + localização via ipinfo
# ----------------------
def get_client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        ip = xff.split(",")[0].strip()
    else:
        ip = request.remote_addr or ""
    return ip

def lookup_ip_info(ip):
    if not ip:
        return ("", "", "")
    try:
        r = requests.get(f"https://ipinfo.io/{ip}/json", timeout=3)
        if r.ok:
            data = r.json()
            city = data.get("city", "")
            region = data.get("region", "")
            country = data.get("country", "")
            loc = ", ".join([x for x in (city, region) if x])
            return (ip, loc, country)
    except Exception:
        pass
    return (ip, "", "")

# ----------------------
# ROTAS
# ----------------------

@app.route("/")
def index():
    # Gera QR dinâmico sempre que abrir index (ou você pode cachear)
    token = gerar_token()
    host = request_host()
    qr_url = f"{host}/presenca?token={token}"
    img = qrcode.make(qr_url)
    os.makedirs("static", exist_ok=True)
    img.save(QR_FILENAME)
    # mostra QR e TTL
    ttl = TOKEN_TTL_SECONDS
    return render_template("index.html", imagem_qrcode=QR_FILENAME, token=token, ttl=ttl)

@app.route("/presenca", methods=["GET", "POST"])
def presenca():
    # aceita GET (com token) para exibir formulário e POST para enviar dados
    token = request.args.get("token") or request.form.get("token")
    if not token_valido(token):
        return render_template("erro.html", mensagem="QR Code inválido ou expirado. Solicite um novo QR Code."), 400

    if request.method == "POST":
        # coleta dados do formulário com .get para evitar KeyError
        nome = request.form.get("nome", "").strip()
        matricula = request.form.get("matricula", "").strip()
        setor = request.form.get("setor", "").strip()

        if not (nome and matricula and setor):
            return render_template("presenca.html", sucesso=False, erro="Preencha todos os campos.", token=token), 400

        # verifica duplicidade no mesmo dia (formato dd/mm/YYYY)
        registros = planilha.get_all_records()
        df = pd.DataFrame(registros) if registros else pd.DataFrame(columns=["Nome Completo","Matrícula","Setor","Data/Hora","IP","Cidade/Estado","País"])
        hoje_str = datetime.now().strftime("%d/%m/%Y")
        duplicado = False
        if not df.empty and "Matrícula" in df.columns and "Data/Hora" in df.columns:
            # extrai somente a data e comparar com hoje
            df["Data"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
            duplicado = ((df["Matrícula"].astype(str) == matricula) & (df["Data"] == hoje_str)).any()

        if duplicado:
            return render_template("presenca.html", sucesso=False, erro="Presença já registrada hoje para esta matrícula.", token=token), 409

        # IP + localização
        ip = get_client_ip()
        ip, cidade_estado, pais = lookup_ip_info(ip)

        datahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        # append na planilha (ordem: Nome | Matrícula | Setor | Data/Hora | IP | Cidade/Estado | País)
        planilha.append_row([nome, matricula, setor, datahora, ip, cidade_estado, pais])

        # confirmação visual
        return render_template("presenca.html", sucesso=True, nome=nome, matricula=matricula, datahora=datahora, ip=ip, local=cidade_estado, pais=pais)

    # GET -> exibe formulário
    return render_template("presenca.html", sucesso=False, token=token)

# Admin simples: login / painel
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")
        if usuario == os.environ.get("ADMIN_USER", "admin") and senha == os.environ.get("ADMIN_PASS", "1234"):
            session["usuario"] = usuario
            return redirect(url_for("admin"))
        return render_template("login.html", erro=True)
    return render_template("login.html", erro=False)

@app.route("/admin")
def admin():
    if "usuario" not in session:
        return redirect(url_for("login"))
    # Dados serão carregados via AJAX para os gráficos
    return render_template("admin.html")

@app.route("/admin/data")
def admin_data():
    if "usuario" not in session:
        return jsonify({"error":"unauthorized"}), 401
    registros = planilha.get_all_records()
    df = pd.DataFrame(registros) if registros else pd.DataFrame(columns=["Nome Completo","Matrícula","Setor","Data/Hora","IP","Cidade/Estado","País"])
    if not df.empty and "Data/Hora" in df.columns:
        df["Data"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
    else:
        df["Data"] = []
    # presencas por dia
    by_day = df.groupby("Data").size().reset_index(name="count").sort_values("Data")
    # por setor
    by_setor = df.groupby("Setor").size().reset_index(name="count").sort_values("count", ascending=False)
    # enviar registros brutos também para tabela
    records = df.to_dict(orient="records")
    return jsonify({
        "by_day": by_day.to_dict(orient="records"),
        "by_setor": by_setor.to_dict(orient="records"),
        "records": records
    })

@app.route("/export")
def export_csv():
    if "usuario" not in session:
        return redirect(url_for("login"))
    registros = planilha.get_all_records()
    df = pd.DataFrame(registros) if registros else pd.DataFrame()
    stream = BytesIO()
    df.to_csv(stream, index=False)
    stream.seek(0)
    resp = make_response(stream.read())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=presencas.csv"
    return resp

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("index"))

# ----------------------
# RUN
# ----------------------
if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)
