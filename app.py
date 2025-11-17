import os
import json
import qrcode
import requests
import secrets
import io
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for, session,
    jsonify, make_response, send_file
)
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from waitress import serve
import pytz

# -------------------------
# CONFIG
# -------------------------
TOKEN_TTL_SECONDS = int(os.environ.get("TOKEN_TTL_SECONDS", "120"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://lista-presenca-kdwr.onrender.com")
SHEET_NAME = os.environ.get("SHEET_NAME", "Lista de Presença")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "C0rd1tram")
FLASK_SECRET = os.environ.get("FLASK_SECRET", "chave_secreta_segura")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = FLASK_SECRET

# -------------------------
# Google Sheets auth
# -------------------------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
# GOOGLE_CREDS_JSON must contain the full JSON string of the service account
credenciais_dict = json.loads(os.environ["GOOGLE_CREDS_JSON"])
credenciais = ServiceAccountCredentials.from_json_keyfile_dict(credenciais_dict, SCOPE)
cliente = gspread.authorize(credenciais)
sheet = cliente.open(SHEET_NAME).sheet1

# -------------------------
# Tokens (in-memory)
# -------------------------
valid_tokens = {}  # token -> expiry (UTC datetime)

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
    expired = [t for t,e in valid_tokens.items() if e < agora]
    for t in expired:
        del valid_tokens[t]

# -------------------------
# Helpers: sheet -> DataFrame
# -------------------------
def read_sheet_df():
    regs = sheet.get_all_records()
    if not regs:
        cols = ["Nome","Matrícula","Setor","Data/Hora","IP"]
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(regs)

# -------------------------
# Config sheet helpers (aba "Config")
# -------------------------
def ensure_config_sheet():
    try:
        ws = cliente.open(SHEET_NAME).worksheet("Config")
    except Exception:
        sh = cliente.open(SHEET_NAME)
        ws = sh.add_worksheet(title="Config", rows="50", cols="2")
        ws.append_row(["key", "value"])
    return ws

def get_config():
    ws = ensure_config_sheet()
    rows = ws.get_all_values()
    config = {}
    for r in rows[1:]:
        if len(r) >= 2:
            k = str(r[0]).strip()
            v = str(r[1]).strip()
            if k:
                config[k] = v
    return config

def set_config(updates: dict):
    ws = ensure_config_sheet()
    rows = ws.get_all_values()
    keys = [r[0] for r in rows]
    # header is row index 1
    for k, v in updates.items():
        if k in keys:
            idx = keys.index(k) + 1  # 0-based -> +1
            # update_cell expects 1-based; header is row 1 so actual row = idx+1
            ws.update_cell(idx + 1, 2, v)
        else:
            ws.append_row([k, v])
    return True

# -------------------------
# QR generation
# -------------------------
def gerar_qrcode_arquivo(token):
    url = f"{PUBLIC_URL}/presenca?token={token}"
    img = qrcode.make(url)
    os.makedirs("static", exist_ok=True)
    path = os.path.join("static", "qrcode.png")
    img.save(path)
    return path

# -------------------------
# IP + geo (ip-api.com)
# -------------------------
def get_client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or ""

def lookup_ip_info(ip):
    if not ip:
        return "", "", ""
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status", timeout=3)
        d = r.json()
        if d.get("status") == "success":
            city = d.get("city", "")
            region = d.get("regionName", "")
            country = d.get("country", "")
            city_region = "/".join([x for x in (city, region) if x])
            return ip, city_region, country
    except Exception:
        pass
    return ip, "", ""

# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    limpar_tokens_expirados()
    token = gerar_token()
    qr_path = gerar_qrcode_arquivo(token)
    return render_template("index.html", imagem_qrcode=qr_path, token=token, ttl=TOKEN_TTL_SECONDS)

@app.route("/presenca", methods=["GET","POST"])
def presenca():
    token = request.args.get("token") or request.form.get("token")
    if not token_valido(token):
        return render_template("erro.html", mensagem="QR Code inválido ou expirado. Gere um novo QR."), 400

    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        matricula = request.form.get("matricula","").strip()
        setor = request.form.get("setor","").strip()

        if not (nome and matricula and setor):
            return render_template("presenca.html", sucesso=False, erro="Preencha todos os campos.", token=token), 400

        # hora Brasília
        tz = pytz.timezone("America/Sao_Paulo")
        agora = datetime.now(tz)
        datahora = agora.strftime("%d/%m/%Y %H:%M:%S")
        hoje = agora.strftime("%d/%m/%Y")

        # ip real + geo
        ip = get_client_ip()
        ip, cidade_estado, pais = lookup_ip_info(ip)

        # duplicidade no mesmo dia
        df = read_sheet_df()
        if not df.empty and "Matrícula" in df.columns and "Data/Hora" in df.columns:
            df["Data"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
            duplicado = ((df["Matrícula"].astype(str) == str(matricula)) & (df["Data"] == hoje)).any()
            if duplicado:
                last = df[(df["Matrícula"].astype(str)==str(matricula)) & (df["Data"]==hoje)]
                last_time = last["Data/Hora"].iloc[-1] if not last.empty else ""
                return render_template("presenca.html", sucesso=False, erro="Presença já registrada hoje.", nome=nome, hora=last_time), 409

        # append (ordem correta)
        sheet.append_row([nome, matricula, setor, datahora, ip, cidade_estado, pais])

        config = get_config()
        tema = config.get("tema", "")
        assinatura = config.get("assinatura", "")

        return render_template("presenca.html",
                               sucesso=True,
                               nome=nome,
                               matricula=matricula,
                               datahora=datahora,
                               ip=ip,
                               tema=tema,
                               assinatura=assinatura)

    return render_template("presenca.html", sucesso=False, token=token)

# -------------------------
# Admin / Login
# -------------------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("usuario")
        p = request.form.get("senha")
        if u == ADMIN_USER and p == ADMIN_PASS:
            session["usuario"] = u
            return redirect(url_for("admin"))
        return render_template("login.html", erro=True)
    return render_template("login.html", erro=False)

@app.route("/admin")
def admin():
    if "usuario" not in session:
        return redirect(url_for("login"))
    config = get_config()
    return render_template("admin.html", config=config)

@app.route("/admin/data")
def admin_data():
    if "usuario" not in session:
        return jsonify({"error":"unauthorized"}), 401

    nome_q = request.args.get("nome","").strip().lower()
    data_from = request.args.get("data_from","").strip()
    data_to = request.args.get("data_to","").strip()

    df = read_sheet_df()
    if df.empty:
        return jsonify({"by_day":[], "by_month":[], "by_setor":[], "records":[]})

    for c in ["Nome","Matrícula","Setor","Data/Hora","IP"]:
        if c not in df.columns:
            df[c] = ""

    # filters
    if nome_q:
        df = df[df["Nome"].astype(str).str.lower().str.contains(nome_q)]
    if data_from:
        df["DataOnly"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
        df = df[df["DataOnly"] >= data_from]
    if data_to:
        df["DataOnly"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
        df = df[df["DataOnly"] <= data_to]

    df["Data"] = df["Data/Hora"].astype(str).str.split(" ").str[0]

    by_day = df.groupby("Data").size().reset_index(name="count").sort_values("Data")
    def to_month(s):
        try:
            d = datetime.strptime(s.split(" ")[0], "%d/%m/%Y")
            return d.strftime("%Y-%m")
        except:
            return ""
    df["Month"] = df["Data/Hora"].astype(str).apply(lambda s: to_month(s))
    by_month = df.groupby("Month").size().reset_index(name="count").sort_values("Month")
    by_setor = df.groupby("Setor").size().reset_index(name="count").sort_values("count", ascending=False)

    records = df.to_dict(orient="records")
    return jsonify({
        "by_day": by_day.to_dict(orient="records"),
        "by_month": by_month.to_dict(orient="records"),
        "by_setor": by_setor.to_dict(orient="records"),
        "records": records
    })

# Save config route
@app.route("/admin/config", methods=["POST"])
def admin_config():
    if "usuario" not in session:
        return jsonify({"error":"unauthorized"}), 401

    tema = request.form.get("tema", "").strip()
    assinatura = request.form.get("assinatura", "").strip()

    updates = {}
    if tema != "":
        updates["tema"] = tema
    if assinatura != "":
        updates["assinatura"] = assinatura

    if updates:
        set_config(updates)

    return redirect(url_for("admin"))

# -------------------------
# Export CSV
# -------------------------
@app.route("/export")
def export_csv():
    if "usuario" not in session:
        return redirect(url_for("login"))

    nome_q = request.args.get("nome","").strip().lower()
    data_from = request.args.get("data_from","").strip()
    data_to = request.args.get("data_to","").strip()

    df = read_sheet_df()
    if df.empty:
        resp = make_response("", 200)
        resp.headers["Content-Type"] = "text/csv"
        resp.headers["Content-Disposition"] = "attachment; filename=presencas.csv"
        return resp

    if nome_q:
        df = df[df["Nome"].astype(str).str.lower().str.contains(nome_q)]
    if data_from:
        df["DataOnly"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
        df = df[df["DataOnly"] >= data_from]
    if data_to:
        df["DataOnly"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
        df = df[df["DataOnly"] <= data_to]

    stream = io.StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)
    resp = make_response(stream.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=presencas.csv"
    return resp

# -------------------------
# Export PDF (ReportLab)
# -------------------------
@app.route("/export_pdf")
def export_pdf():
    if "usuario" not in session:
        return redirect(url_for("login"))

    nome_q = request.args.get("nome","").strip().lower()
    data_from = request.args.get("data_from","").strip()
    data_to = request.args.get("data_to","").strip()

    df = read_sheet_df()
    if df.empty:
        pdf_buf = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buf, pagesize=landscape(A4))
        doc.build([])
        pdf_buf.seek(0)
        return send_file(pdf_buf, as_attachment=True, download_name="presencas.pdf", mimetype="application/pdf")

    if nome_q:
        df = df[df["Nome"].astype(str).str.lower().str.contains(nome_q)]
    if data_from:
        df["DataOnly"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
        df = df[df["DataOnly"] >= data_from]
    if data_to:
        df["DataOnly"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
        df = df[df["DataOnly"] <= data_to]

    cols = ["Nome","Matrícula","Setor","Data/Hora","IP","Cidade/Estado","País"]
    data = [cols]
    for _, row in df.iterrows():
        data.append([row.get(c,"") for c in cols])

    # append empty row and config
    config = get_config()
    tema_val = config.get("tema", "")
    assin_val = config.get("assinatura", "")

    data.append([''] * len(cols))
    if tema_val:
        line = ["Tema:", tema_val] + [''] * (len(cols)-2)
        data.append(line)
    if assin_val:
        line = ["Assinatura:", assin_val] + [''] * (len(cols)-2)
        data.append(line)

    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buf, pagesize=landscape(A4))
    style = TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#f2f2f2")),
        ('GRID',(0,0),(-1,-1),0.25,colors.black),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
    ])
    table = Table(data, repeatRows=1)
    table.setStyle(style)
    elems = [table]
    doc.build(elems)
    pdf_buf.seek(0)
    return send_file(pdf_buf, as_attachment=True, download_name="presencas.pdf", mimetype="application/pdf")

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("index"))

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)


