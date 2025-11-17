# app.py
import os, io
from flask import (
    Flask, render_template, request, redirect, url_for, jsonify, send_file, make_response
)
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

from qr_token import token_atual, gerar_token, validar_token, segundos_restantes, invalidar_token
import google_api as gapi

app = Flask(__name__, static_folder="static", static_url_path="/static")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "C0rditran")

HEADERS = ["Nome", "Matrícula", "Setor", "Data/Hora", "IP"]

def read_df():
    recs = gapi.get_all_records()
    if not recs:
        return pd.DataFrame(columns=HEADERS)
    return pd.DataFrame(recs)

def append_presence(nome, matricula, setor, ip):
    ts = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
    gapi.append_row([nome, matricula, setor, ts, ip])
    return ts

def count_today():
    df = read_df()
    if df.empty: return 0
    hoje = datetime.now().strftime("%d/%m/%Y")
    data = df["Data/Hora"].astype(str).str.split(" ").str[0]
    return int((data == hoje).sum())

@app.route("/")
def index():
    # mantém o QR fixo gerado em static/qrcode.png (compatível com sua versão anterior)
    return render_template("index.html", imagem_qrcode="static/qrcode.png")

@app.route("/presenca", methods=["GET","POST"])
def presenca():
    token = request.args.get("token") or request.form.get("token")
    # valida token (se for acessado por QR com token)
    if token and not validar_token(token):
        return render_template("erro.html", mensagem="QR expirado ou inválido."), 400

    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        matricula = request.form.get("matricula","").strip()
        setor = request.form.get("setor","").strip()
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)

        if not (nome and matricula and setor):
            return render_template("presenca.html", sucesso=False, erro="Preencha todos os campos.", token=token), 400

        if gapi.ja_registrado_hoje(matricula):
            return render_template("duplicate.html", nome=nome), 409

        ts = append_presence(nome, matricula, setor, ip)
        return render_template("presenca.html", sucesso=True, nome=nome, matricula=matricula, datahora=ts, ip=ip)

    return render_template("presenca.html", sucesso=False, token=token_atual())

# Admin login simple via ?senha=
@app.route("/admin")
def admin():
    senha = request.args.get("senha","")
    if senha != ADMIN_PASSWORD:
        return render_template("login.html", erro=False)
    token = token_atual()
    ttl = segundos_restantes()
    contador = count_today()
    return render_template("admin.html", token=token, ttl=ttl, contador=contador, senha=senha)

@app.route("/admin/data")
def admin_data():
    senha = request.args.get("senha","")
    if senha != ADMIN_PASSWORD:
        return jsonify({"error":"unauthorized"}), 401
    nome = request.args.get("nome","").strip()
    date_from = request.args.get("date_from","").strip()
    date_to = request.args.get("date_to","").strip()

    df = read_df()
    if not df.empty:
        if nome:
            df = df[df["Nome"].str.lower().str.contains(nome.lower())]
        if date_from:
            df = df[df["Data/Hora"].str.split(" ").str[0] >= date_from]
        if date_to:
            df = df[df["Data/Hora"].str.split(" ").str[0] <= date_to]

    # aggregations
    if df.empty:
        return jsonify({"by_day":[], "by_month":[], "by_setor":[], "records":[], "contador":0})
    df["Data"] = df["Data/Hora"].str.split(" ").str[0]
    by_day = df.groupby("Data").size().reset_index(name="count").sort_values("Data")
    def to_month(x):
        try:
            d = datetime.strptime(x, "%d/%m/%Y")
            return d.strftime("%Y-%m")
        except:
            return ""
    df["Month"] = df["Data"].apply(to_month)
    by_month = df.groupby("Month").size().reset_index(name="count").sort_values("Month")
    by_setor = df.groupby("Setor").size().reset_index(name="count").sort_values("count", ascending=False)
    records = df.to_dict(orient="records")
    contador = int((df["Data"] == datetime.now().strftime("%d/%m/%Y")).sum())
    return jsonify({
        "by_day": by_day.to_dict(orient="records"),
        "by_month": by_month.to_dict(orient="records"),
        "by_setor": by_setor.to_dict(orient="records"),
        "records": records,
        "contador": contador
    })

@app.route("/export_csv")
def export_csv():
    senha = request.args.get("senha","")
    if senha != ADMIN_PASSWORD:
        return redirect(url_for("admin"))
    nome = request.args.get("nome","").strip()
    date_from = request.args.get("date_from","").strip()
    date_to = request.args.get("date_to","").strip()
    df = read_df()
    if not df.empty:
        if nome:
            df = df[df["Nome"].str.lower().str.contains(nome.lower())]
        if date_from:
            df = df[df["Data/Hora"].str.split(" ").str[0] >= date_from]
        if date_to:
            df = df[df["Data/Hora"].str.split(" ").str[0] <= date_to]
    out = io.StringIO()
    df.to_csv(out, index=False)
    out.seek(0)
    resp = make_response(out.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=presencas.csv"
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    return resp

@app.route("/export_pdf")
def export_pdf():
    senha = request.args.get("senha","")
    if senha != ADMIN_PASSWORD:
        return redirect(url_for("admin"))
    df = read_df()
    data = [HEADERS]
    for _, r in df.iterrows():
        data.append([r.get(c,"") for c in HEADERS])
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
    style = TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor("#f2f2f2")), ('GRID',(0,0),(-1,-1),0.25,colors.black)])
    table = Table(data, repeatRows=1)
    table.setStyle(style)
    doc.build([table])
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="presencas.pdf", mimetype="application/pdf")

# token API & invalidate
@app.route("/api/token")
def api_token():
    return jsonify({"token": token_atual(), "ttl": segundos_restantes(), "contador": count_today()})

@app.route("/admin/invalidate_token", methods=["POST"])
def admin_invalidate_token():
    senha = request.form.get("senha","")
    if senha != ADMIN_PASSWORD:
        return jsonify({"error":"unauthorized"}), 401
    new = invalidar_token()
    return jsonify({"token": new, "ttl": segundos_restantes()})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","8080")))

