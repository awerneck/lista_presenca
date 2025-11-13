from flask import Flask, render_template, request, redirect, url_for, session
import qrcode, os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = 'chave-super-secreta'

# Configuração de admin
ADMIN_USER = 'admin'
ADMIN_PASS = '1234'

# Configuração do Google Sheets
PLANILHA_NOME = "Controle de Presença"

def conectar_sheets():
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open(PLANILHA_NOME).sheet1


# ---------- Funções principais ----------

def gerar_qrcode():
    url = "http://localhost:5000/presenca"
    img = qrcode.make(url)
    os.makedirs("static", exist_ok=True)
    img.save("static/qrcode.png")

def registrar_presenca(nome, matricula, setor):
    planilha = conectar_sheets()
    data = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    planilha.append_row([nome, matricula, setor, data])

def carregar_presencas():
    planilha = conectar_sheets()
    return planilha.get_all_values()


# ---------- Rotas ----------

@app.route('/')
def index():
    gerar_qrcode()
    return render_template('index.html')

@app.route('/presenca', methods=['GET', 'POST'])
def presenca():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        matricula = request.form.get('matricula', '').strip()
        setor = request.form.get('setor', '').strip()

        if not nome or not matricula or not setor:
            return render_template('presenca.html', erro="Preencha todos os campos.", confirmacao=False)

        registrar_presenca(nome, matricula, setor)
        return render_template('presenca.html', confirmacao=True, nome=nome)

    return render_template('presenca.html', confirmacao=False)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        senha = request.form.get('senha')

        if usuario == ADMIN_USER and senha == ADMIN_PASS:
            session['admin'] = True
            return redirect(url_for('admin'))
        else:
            return render_template('login.html', erro="Usuário ou senha inválidos.")
    return render_template('login.html')


@app.route('/admin', methods=['GET'])
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))

    termo = request.args.get('termo', '').strip().lower()
    data_filtro = request.args.get('data', '').strip()
    presencas = carregar_presencas()

    cabecalho = presencas[0] if presencas else []
    registros = presencas[1:] if len(presencas) > 1 else []

    if termo or data_filtro:
        registros = [
            r for r in registros
            if (termo in ' '.join(r).lower()) and (data_filtro in r[3] if data_filtro else True)
        ]

    return render_template('admin.html', presencas=[cabecalho] + registros, termo=termo, data=data_filtro)


@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('login'))


if __name__ == '__main__':
    from waitress import serve
    serve(app, host="0.0.0.0", port=8080)

