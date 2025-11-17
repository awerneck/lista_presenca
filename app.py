# app.py
import os
import io
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_file, make_response
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
import pandas as pd

from qr_token import token_atual, gerar_token, validar_token, segundos_restantes, invalidar_token

# ---------- CONFIG ----------
app = Flask(__name__, static_folder="static", static_url_path="/static")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "C0rditran")
SHEET_NAME = os.environ.get("SHEET_NAME", "Lista de Presença")
# Google creds: variável de ambiente contendo JSON string
GCP_JSON = os.environ.get("GOOGLE_CREDS_JSON")

# ---------- Google Sheets setup ----------
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = None
if GCP_JSON:
    import json
    creds_dict = json.loads(GCP_JSON)

if creds_dict:
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(credentials)
    sheet = client.open(SHEET_NAME).sheet1
else:
    sheet = None

HEADERS = ["Nome", "Matrícula", "Setor", "Data/Hora", "IP"]

def ensure_headers():
    global sheet
    if not sheet:
        return
    try:
        first = sheet.row_values(1)
        if not first or first[0] != "Nome":
            sheet.insert_row(HEADERS, 1)
    except Exception:
        pass

ensure_headers()

# ---------- Helpers ----------
def read_df():
    try:
        rows = sheet.get_all_records()
        if not rows:
            return pd.DataFrame(columns=HEADERS)
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame(columns=HEADERS)

def append_row(row):
    sheet.append_row(row)

def count_today():
    df = read_df()
    if df.empty or "Data/Hora" not in df.columns:
        return 0
    try:
        # compara data (dd/mm/YYYY)
        tz_today = datetime.now().strftime("%d/%m/%Y")
        data_only = df["Data/Hora"].astype(str).str.split(" ").str[0]
        return int((data_only == tz_today).sum())
    except Exception:
        return 0

def filter_df_by_params(nome_q="", date_from="", date_to=""):
    df = read_df()
    if df.empty:
        return df
    if nome_q:
        df = df[df["Nome"].astype(str).str.lower().str.contains(nome_q.lower())]
    if date_from:
        df["DataOnly"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
        df = df[df["DataOnly"] >= date_from]
    if date_to:
        df["DataOnly"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
        df = df[df["DataOnly"] <= date_to]
    return df

def ja_registrado_hoje(matricula):
    df = read_df()
    if df.empty:
        return False
    hoje = datetime.now().strftime("%d/%m/%Y")
    df["DataOnly"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
    return ((df["Matrícula"].astype(str) == str(matricula)) & (df["DataOnly"] == hoje)).any()

# ---------- Routes ----------
@app.route("/")
def index():
    t = token_atual()
    ttl = segundos_restantes()
    qr_path = "/static/qrcode.png"  # gerado no front-end via token
    return render_template("index.html", token=t, ttl=ttl, imagem_qrcode=qr_path)

@app.route("/presenca", methods=["GET","POST"])
def presenca():
    token = request.args.get("token") or request.form.get("token")
    if not validar_token(token):
        return render_template("erro.html", mensagem="QR Code inválido ou expirado. Gere um novo QR."), 400

    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        matricula = request.form.get("matricula","").strip()
        setor = request.form.get("setor","").strip()
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)

        # valida campos
        if not (nome and matricula and setor):
            return render_template("presenca.html", sucesso=False, erro="Preencha todos os campos.", token=token), 400

        # duplicidade
        if ja_registrado_hoje(matricula):
            return render_template("duplicate.html", nome=nome), 409

        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        append_row([nome, matricula, setor, timestamp, ip])
        return render_template("presenca.html", sucesso=True, nome=nome, matricula=matricula, datahora=timestamp, ip=ip)

    return render_template("presenca.html", sucesso=False, token=token)

# Admin (acesso por ?senha=)
@app.route("/admin")
def admin():
    senha = request.args.get("senha", "")
    if senha != ADMIN_PASSWORD:
        return render_template("login.html", erro=False)
    # Passa token atual, contador do dia
    token = token_atual()
    ttl = segundos_restantes()
    contador = count_today()
    return render_template("admin.html", token=token, ttl=ttl, contador=contador)

# API para dados do admin (charts + tabela)
@app.route("/admin/data")
def admin_data():
    senha = request.args.get("senha", "")
    if senha != ADMIN_PASSWORD:
        return jsonify({"error":"unauthorized"}), 401

    nome_q = request.args.get("nome","").strip().lower()
    date_from = request.args.get("date_from","").strip()
    date_to = request.args.get("date_to","").strip()

    df = filter_df_by_params(nome_q, date_from, date_to)
    if df.empty:
        return jsonify({"by_day":[], "by_month":[], "by_setor":[], "records":[]})

    # preparar agregações
    df["Data"] = df["Data/Hora"].astype(str).str.split(" ").str[0]
    by_day = df.groupby("Data").size().reset_index(name="count").sort_values("Data")
    def to_month(s):
        try:
            d = datetime.strptime(s, "%d/%m/%Y")
            return d.strftime("%Y-%m")
        except:
            return ""
    df["Month"] = df["Data"].apply(lambda s: to_month(s))
    by_month = df.groupby("Month").size().reset_index(name="count").sort_values("Month")
    by_setor = df.groupby("Setor").size().reset_index(name="count").sort_values("count", ascending=False)

    return jsonify({
        "by_day": by_day.to_dict(orient="records"),
        "by_month": by_month.to_dict(orient="records"),
        "by_setor": by_setor.to_dict(orient="records"),
        "records": df.to_dict(orient="records"),
        "contador": int((df["Data"] == datetime.now().strftime("%d/%m/%Y")).sum()) if not df.empty else 0
    })

# Export CSV (com filtros)
@app.route("/export_csv")
def export_csv():
    senha = request.args.get("senha", "")
    if senha != ADMIN_PASSWORD:
        return redirect(url_for("admin"))
    nome_q = request.args.get("nome","").strip().lower()
    date_from = request.args.get("date_from","").strip()
    date_to = request.args.get("date_to","").strip()
    df = filter_df_by_params(nome_q, date_from, date_to)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)
    resp = make_response(stream.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=presencas.csv"
    return resp

# Export PDF (mantido)
@app.route("/export_pdf")
def export_pdf():
    senha = request.args.get("senha", "")
    if senha != ADMIN_PASSWORD:
        return redirect(url_for("admin"))
    nome_q = request.args.get("nome","").strip().lower()
    date_from = request.args.get("date_from","").strip()
    date_to = request.args.get("date_to","").strip()
    df = filter_df_by_params(nome_q, date_from, date_to)
    cols = HEADERS
    data = [cols]
    for _, row in df.iterrows():
        data.append([row.get(c,"") for c in cols])

    # PDF build
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
    style = TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#f2f2f2")),
        ('GRID',(0,0),(-1,-1),0.25,colors.black),
    ])
    table = Table(data, repeatRows=1)
    table.setStyle(style)
    doc.build([table])
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="presencas.pdf", mimetype="application/pdf")

# API token (para frontend atualizar QR / contador)
@app.route("/api/token")
def api_token():
    return jsonify({"token": token_atual(), "ttl": segundos_restantes(), "contador": count_today()})

# Invalida token (gerar novo) - protegido por senha
@app.route("/admin/invalidate_token", methods=["POST"])
def admin_invalidate_token():
    senha = request.form.get("senha","")
    if senha != ADMIN_PASSWORD:
        return jsonify({"error":"unauthorized"}), 401
    new = invalidar_token()
    return jsonify({"token": new, "ttl": segundos_restantes()})

# Logout route convenience (not session-based here)
@app.route("/logout")
def logout():
    return redirect(url_for("index"))

# ---------- Run ----------
if __name__ == "__main__":
    # em produção use gunicorn; para testes
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
