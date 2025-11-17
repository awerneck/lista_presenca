from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from google_api import registrar_presenca, get_presencas, ja_registrado_hoje
from qr_token import validar_token, gerar_token, token_atual
from datetime import datetime
import io
from reportlab.pdfgen import canvas

app = Flask(__name__)
ADMIN_PASSWORD = "C0rditran"


@app.route("/")
def index():
    token = gerar_token()
    return render_template("index.html", token=token)


@app.route("/presenca", methods=["GET", "POST"])
def presenca():
    token = request.args.get("token") or request.form.get("token")

    if not validar_token(token):
        return render_template("token_expirado.html")

    if request.method == "POST":
        nome = request.form.get("nome")
        matricula = request.form.get("matricula")
        setor = request.form.get("setor")
        ip = request.remote_addr

        if ja_registrado_hoje(matricula):
            return render_template("duplicate.html", nome=nome)

        registrar_presenca(nome, matricula, setor, ip)
        return render_template("success.html", nome=nome)

    return render_template("presenca.html", token=token_atual())


@app.route("/admin", methods=["GET"])
def admin():
    senha = request.args.get("senha", "")
    if senha != ADMIN_PASSWORD:
        return render_template("admin_login.html")

    token = token_atual()
    presencas = get_presencas()
    return render_template("admin.html", presencas=presencas, token=token)


@app.route("/admin/pdf")
def export_pdf():
    presencas = get_presencas()
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    pdf.setTitle("Lista de Presença")

    for p in presencas[1:]:
        texto = f"{p[0]} | {p[1]} | {p[2]} | {p[3]} | {p[4]}"
        pdf.drawString(25, y, texto)
        y -= 18

    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="lista_presenca.pdf")


@app.route("/api/graficos")
def dados_graficos():
    presencas = get_presencas()[1:]
    setores, meses, dias = {}, {}, {}

    for p in presencas:
        setor = p[2]
        data = datetime.strptime(p[3], "%d/%m/%Y %H:%M:%S")
        mes = data.strftime("%m/%Y")
        dia = data.strftime("%d/%m/%Y")
        setores[setor] = setores.get(setor, 0) + 1
        meses[mes] = meses.get(mes, 0) + 1
        dias[dia] = dias.get(dia, 0) + 1

    return jsonify({"setores": setores, "meses": meses, "dias": dias})


@app.route("/api/token")
def api_token():
    return jsonify({"token": token_atual()})


if __name__ == "__main__":
    app.run(host="0.0.0.0")
