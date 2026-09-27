import os
import re
import json
import uuid
import calendar
import sqlite3
import urllib.request
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask, request, session, redirect, url_for, render_template,
    g, flash, send_from_directory, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import pdfplumber

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "financas.db")
SECRET_PATH = os.path.join(BASE_DIR, "secret.key")
COMPROVANTES_DIR = os.path.join(BASE_DIR, "comprovantes")
SONHOS_DIR = os.path.join(BASE_DIR, "sonhos")
os.makedirs(COMPROVANTES_DIR, exist_ok=True)
os.makedirs(SONHOS_DIR, exist_ok=True)

ALLOWED_COMPROVANTE_EXT = {"pdf", "jpg", "jpeg", "png", "webp"}
ALLOWED_SONHO_EXT = {"jpg", "jpeg", "png", "webp", "gif"}

# --- chave secreta persistente (para as sessões/login continuarem válidas entre reinícios) ---
if not os.path.exists(SECRET_PATH):
    with open(SECRET_PATH, "wb") as f:
        f.write(os.urandom(32))
with open(SECRET_PATH, "rb") as f:
    SECRET_KEY = f.read()

app = Flask(__name__)
app.secret_key = SECRET_KEY

DEFAULT_CATEGORIES = [
    "Mercado", "Essencial", "Moradia", "Transporte", "Saúde",
    "Educação", "Lazer", "Assinaturas", "Salário", "Freelance",
    "Investimento", "Outros",
]

TIPOS_INVESTIMENTO = [
    "CDI Fixo", "Selic", "Poupança", "Variável",
    "Fundo de Investimento Variável", "Outro",
]

NOISE_WORDS = {
    "COMPRA", "DEBITO", "DÉBITO", "CREDITO", "CRÉDITO", "PARCELA", "PARC",
    "CARTAO", "CARTÃO", "PAGAMENTO", "PGTO", "TRANSFERENCIA", "TRANSFERÊNCIA",
    "PIX", "DE", "EM", "PARA", "A", "O", "DA", "DO", "LTDA", "ME", "EIRELI",
    "S/A", "SA", "NACIONAL", "INTERNACIONAL",
}

# Paletas de cores (tema) e fundos disponíveis para personalização por perfil
THEMES = {
    "roxo":    {"label": "Roxo (padrão)", "primary": "#6c5ce7", "secondary": "#00b894", "accent": "#fdcb6e"},
    "rosa":    {"label": "Rosa",          "primary": "#e84393", "secondary": "#fd79a8", "accent": "#ffb8d9"},
    "azul":    {"label": "Azul",          "primary": "#0984e3", "secondary": "#00cec9", "accent": "#74b9ff"},
    "verde":   {"label": "Verde",         "primary": "#00b894", "secondary": "#55efc4", "accent": "#a4de6c"},
    "laranja": {"label": "Laranja",       "primary": "#e17055", "secondary": "#fdcb6e", "accent": "#ffa06b"},
}

BACKGROUNDS = {
    "branco": {"label": "Branco simples",     "css": "#f7f7fb"},
    "rosa":   {"label": "Gradiente rosa",     "css": "linear-gradient(135deg,#ffe4ef 0%,#fff0f5 50%,#ffe9f3 100%)"},
    "azul":   {"label": "Gradiente azul",     "css": "linear-gradient(135deg,#e3f1ff 0%,#f0f8ff 50%,#e8f4ff 100%)"},
    "lilas":  {"label": "Gradiente lilás",    "css": "linear-gradient(135deg,#eee3ff 0%,#f5f0ff 50%,#ece0ff 100%)"},
    "verde":  {"label": "Gradiente verde",    "css": "linear-gradient(135deg,#e3fff0 0%,#f0fff5 50%,#e5fff2 100%)"},
}

MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_MINUTOS = 15


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _garantir_coluna(db, tabela, coluna, declaracao):
    cols = [r[1] for r in db.execute(f"PRAGMA table_info({tabela})").fetchall()]
    if coluna not in cols:
        db.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {declaracao}")


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            color TEXT DEFAULT '#6c5ce7',
            tema TEXT DEFAULT 'roxo',
            fundo TEXT DEFAULT 'branco'
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,              -- entrada | saida | investimento_deposito | investimento_resgate
            valor REAL NOT NULL,
            data TEXT NOT NULL,              -- YYYY-MM-DD
            descricao TEXT NOT NULL,
            categoria TEXT,
            origem TEXT DEFAULT 'manual',    -- manual | pdf | conta_fixa
            comprovante TEXT,
            investimento_id INTEGER,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS category_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            categoria TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contas_fixas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            categoria TEXT,
            responsavel TEXT,
            dia_vencimento INTEGER NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pagamentos_fixos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conta_fixa_id INTEGER NOT NULL,
            competencia TEXT NOT NULL,        -- YYYY-MM
            valor REAL NOT NULL,
            status TEXT DEFAULT 'pendente',   -- pendente | pago
            data_pagamento TEXT,
            comprovante TEXT,
            transaction_id INTEGER,
            UNIQUE(conta_fixa_id, competencia),
            FOREIGN KEY (conta_fixa_id) REFERENCES contas_fixas (id)
        );

        CREATE TABLE IF NOT EXISTS investimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS previsoes_mensais (
            competencia TEXT PRIMARY KEY,
            planejado_gastos REAL DEFAULT 0,
            planejado_ganhos REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sonhos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            legenda TEXT,
            user_id INTEGER NOT NULL,
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS login_attempts (
            username TEXT PRIMARY KEY,
            tentativas INTEGER DEFAULT 0,
            bloqueado_ate TEXT
        );
        """
    )
    db.commit()

    # migrações leves para bancos criados antes desta versão
    _garantir_coluna(db, "transactions", "comprovante", "TEXT")
    _garantir_coluna(db, "transactions", "investimento_id", "INTEGER")
    _garantir_coluna(db, "contas_fixas", "responsavel", "TEXT")
    _garantir_coluna(db, "users", "tema", "TEXT DEFAULT 'roxo'")
    _garantir_coluna(db, "users", "fundo", "TEXT DEFAULT 'branco'")
    db.commit()

    # renomeia o antigo tipo "futuro_*" para "investimento_*" (idempotente)
    db.execute("UPDATE transactions SET tipo='investimento_deposito' WHERE tipo='futuro_deposito'")
    db.execute("UPDATE transactions SET tipo='investimento_resgate' WHERE tipo='futuro_resgate'")
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Ajuda: valores em R$, normalização e aprendizado de categoria
# ---------------------------------------------------------------------------

def parse_valor_brl(texto: str) -> float:
    """Converte strings tipo '1.234,56', '1234,56', '1234.56' ou '1234' em float.
    Lança ValueError se não conseguir interpretar."""
    if texto is None:
        raise ValueError("valor vazio")
    s = str(texto).strip().replace("R$", "").replace(" ", "")
    if not s:
        raise ValueError("valor vazio")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def normalize_desc(desc: str) -> str:
    d = desc.upper()
    d = re.sub(r"\d+", " ", d)
    d = re.sub(r"[^A-ZÀ-Ú\s]", " ", d)
    tokens = [t for t in d.split() if t and t not in NOISE_WORDS and len(t) > 1]
    return " ".join(tokens).strip()


def extract_keyword(desc: str) -> str:
    norm = normalize_desc(desc)
    tokens = norm.split()
    return " ".join(tokens[:3]) if tokens else norm


def guess_category(desc: str):
    db = get_db()
    norm = normalize_desc(desc)
    if not norm:
        return None
    rules = db.execute("SELECT keyword, categoria FROM category_rules").fetchall()
    best = None
    best_len = 0
    for r in rules:
        kw = r["keyword"]
        if kw and (kw in norm or norm in kw):
            if len(kw) > best_len:
                best = r["categoria"]
                best_len = len(kw)
    return best


def learn_category(desc: str, categoria: str):
    if not categoria:
        return
    kw = extract_keyword(desc)
    if not kw:
        return
    db = get_db()
    db.execute(
        "INSERT INTO category_rules (keyword, categoria) VALUES (?, ?) "
        "ON CONFLICT(keyword) DO UPDATE SET categoria=excluded.categoria",
        (kw, categoria),
    )
    db.commit()


def save_upload(file_storage, folder, allowed_ext):
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in allowed_ext:
        return None
    nome_seguro = secure_filename(file_storage.filename)
    fname = f"{uuid.uuid4().hex}_{nome_seguro}"
    file_storage.save(os.path.join(folder, fname))
    return fname


def save_comprovante(file_storage):
    return save_upload(file_storage, COMPROVANTES_DIR, ALLOWED_COMPROVANTE_EXT)


def save_sonho(file_storage):
    return save_upload(file_storage, SONHOS_DIR, ALLOWED_SONHO_EXT)


# ---------------------------------------------------------------------------
# Cotações públicas (Banco Central) — best effort, com cache simples
# ---------------------------------------------------------------------------

_rate_cache = {}


def fetch_taxa_bcb(codigo_serie):
    try:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_serie}/dados/ultimos/1?formato=json"
        with urllib.request.urlopen(url, timeout=3) as resp:
            dados = json.loads(resp.read().decode())
            if dados:
                return dados[0]  # {'data': 'dd/mm/aaaa', 'valor': 'x.xx'}
    except Exception:
        return None
    return None


def fetch_taxa_bcb_cached(codigo_serie, max_age_horas=6):
    agora = datetime.now()
    cache = _rate_cache.get(codigo_serie)
    if cache and (agora - cache["ts"]).total_seconds() < max_age_horas * 3600:
        return cache["data"]
    resultado = fetch_taxa_bcb(codigo_serie)
    _rate_cache[codigo_serie] = {"ts": agora, "data": resultado}
    return resultado


# ---------------------------------------------------------------------------
# Autenticação e limitador de tentativas
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def any_users_exist():
    db = get_db()
    return db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] > 0


def get_attempt(username):
    db = get_db()
    return db.execute("SELECT * FROM login_attempts WHERE username = ?", (username,)).fetchone()


def reset_attempts(username):
    db = get_db()
    db.execute("DELETE FROM login_attempts WHERE username = ?", (username,))
    db.commit()


def register_failed_attempt(username):
    db = get_db()
    row = get_attempt(username)
    if row:
        tentativas = row["tentativas"] + 1
        bloqueado_ate = row["bloqueado_ate"]
        if tentativas >= MAX_TENTATIVAS_LOGIN:
            bloqueado_ate = (datetime.now() + timedelta(minutes=BLOQUEIO_MINUTOS)).isoformat()
            tentativas = 0
        db.execute(
            "UPDATE login_attempts SET tentativas=?, bloqueado_ate=? WHERE username=?",
            (tentativas, bloqueado_ate, username),
        )
    else:
        db.execute("INSERT INTO login_attempts (username, tentativas, bloqueado_ate) VALUES (?, 1, NULL)", (username,))
    db.commit()


def is_blocked(username):
    row = get_attempt(username)
    if row and row["bloqueado_ate"]:
        bloqueado_ate = datetime.fromisoformat(row["bloqueado_ate"])
        if datetime.now() < bloqueado_ate:
            return bloqueado_ate
        reset_attempts(username)
    return None


@app.before_request
def route_setup_gate():
    if request.endpoint in ("setup", "static"):
        return
    if not any_users_exist() and request.endpoint != "setup":
        return redirect(url_for("setup"))


@app.before_request
def load_current_user():
    g.user = None
    if "user_id" in session:
        db = get_db()
        g.user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()


@app.context_processor
def inject_theme():
    tema_key = g.user["tema"] if g.user and g.user["tema"] in THEMES else "roxo"
    fundo_key = g.user["fundo"] if g.user and g.user["fundo"] in BACKGROUNDS else "branco"
    return dict(tema=THEMES[tema_key], fundo=BACKGROUNDS[fundo_key], tema_key=tema_key, fundo_key=fundo_key)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if any_users_exist():
        return redirect(url_for("login"))
    if request.method == "POST":
        db = get_db()
        colors = ["#6c5ce7", "#00b894"]
        for i in (1, 2):
            username = request.form.get(f"username{i}", "").strip().lower()
            display = request.form.get(f"display{i}", "").strip()
            pwd = request.form.get(f"password{i}", "")
            if username and display and pwd:
                db.execute(
                    "INSERT INTO users (username, display_name, password_hash, color) VALUES (?, ?, ?, ?)",
                    (username, display, generate_password_hash(pwd), colors[i - 1]),
                )
        db.commit()
        flash("Contas criadas! Agora é só entrar.", "success")
        return redirect(url_for("login"))
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        bloqueio = is_blocked(username)
        if bloqueio:
            flash(f"Muitas tentativas erradas. Tente novamente após {bloqueio.strftime('%H:%M')}.", "error")
            return render_template("login.html")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            reset_attempts(username)
            session["user_id"] = user["id"]
            session["display_name"] = user["display_name"]
            return redirect(url_for("dashboard"))

        register_failed_attempt(username)
        row = get_attempt(username)
        restantes = max(0, MAX_TENTATIVAS_LOGIN - (row["tentativas"] if row else 0))
        if row and row["bloqueado_ate"]:
            flash(f"Muitas tentativas erradas. Conta bloqueada por {BLOQUEIO_MINUTOS} minutos.", "error")
        else:
            flash(f"Usuário ou senha incorretos. Tentativas restantes: {restantes}.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/comprovantes/<path:filename>")
@login_required
def ver_comprovante(filename):
    return send_from_directory(COMPROVANTES_DIR, filename)


@app.route("/sonhos-fotos/<path:filename>")
@login_required
def ver_sonho_foto(filename):
    return send_from_directory(SONHOS_DIR, filename)


# ---------------------------------------------------------------------------
# Perfil (senha + estilo visual + backup)
# ---------------------------------------------------------------------------

@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    db = get_db()
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "senha":
            atual = request.form.get("senha_atual", "")
            nova = request.form.get("senha_nova", "")
            confirmar = request.form.get("senha_confirmar", "")
            user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
            if not check_password_hash(user["password_hash"], atual):
                flash("Senha atual incorreta.", "error")
            elif len(nova) < 4:
                flash("A nova senha deve ter pelo menos 4 caracteres.", "error")
            elif nova != confirmar:
                flash("A confirmação não bate com a nova senha.", "error")
            else:
                db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(nova), session["user_id"]))
                db.commit()
                flash("Senha atualizada com sucesso!", "success")
        elif acao == "estilo":
            tema_novo = request.form.get("tema", "roxo")
            fundo_novo = request.form.get("fundo", "branco")
            if tema_novo not in THEMES:
                tema_novo = "roxo"
            if fundo_novo not in BACKGROUNDS:
                fundo_novo = "branco"
            db.execute("UPDATE users SET tema = ?, fundo = ? WHERE id = ?", (tema_novo, fundo_novo, session["user_id"]))
            db.commit()
            flash("Estilo visual atualizado!", "success")
        return redirect(url_for("perfil"))
    return render_template("profile.html", THEMES=THEMES, BACKGROUNDS=BACKGROUNDS)


@app.route("/perfil/backup")
@login_required
def baixar_backup():
    if not os.path.exists(DB_PATH):
        flash("Banco de dados ainda não existe.", "error")
        return redirect(url_for("perfil"))
    return send_file(DB_PATH, as_attachment=True, download_name=f"financas_backup_{date.today().isoformat()}.db")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    db = get_db()
    today = date.today()
    month_start = today.replace(day=1).isoformat()

    def total(tipo, since=None):
        q = "SELECT COALESCE(SUM(valor),0) t FROM transactions WHERE tipo = ?"
        params = [tipo]
        if since:
            q += " AND data >= ?"
            params.append(since)
        return db.execute(q, params).fetchone()["t"]

    entradas_mes = total("entrada", month_start)
    saidas_mes = total("saida", month_start)
    saldo_mes = entradas_mes - saidas_mes

    total_investido = total("investimento_deposito") - total("investimento_resgate")

    # gastos por categoria (mês atual)
    cat_rows = db.execute(
        """SELECT COALESCE(categoria,'Outros') categoria, SUM(valor) total
           FROM transactions WHERE tipo='saida' AND data >= ?
           GROUP BY categoria ORDER BY total DESC""",
        (month_start,),
    ).fetchall()
    categorias_labels = [r["categoria"] for r in cat_rows]
    categorias_valores = [round(r["total"], 2) for r in cat_rows]

    # evolução últimos 6 meses (entradas, saídas e investimentos)
    meses_labels, meses_entradas, meses_saidas, meses_investimentos = [], [], [], []
    y, m = today.year, today.month
    months = []
    for i in range(5, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append((yy, mm))
    for yy, mm in months:
        ini = f"{yy:04d}-{mm:02d}-01"
        fim = f"{yy+1:04d}-01-01" if mm == 12 else f"{yy:04d}-{mm+1:02d}-01"
        e = db.execute("SELECT COALESCE(SUM(valor),0) t FROM transactions WHERE tipo='entrada' AND data>=? AND data<?", (ini, fim)).fetchone()["t"]
        s = db.execute("SELECT COALESCE(SUM(valor),0) t FROM transactions WHERE tipo='saida' AND data>=? AND data<?", (ini, fim)).fetchone()["t"]
        inv = db.execute(
            """SELECT COALESCE(SUM(CASE WHEN tipo='investimento_deposito' THEN valor ELSE -valor END),0) t
               FROM transactions WHERE tipo LIKE 'investimento%' AND data>=? AND data<?""",
            (ini, fim),
        ).fetchone()["t"]
        meses_labels.append(f"{mm:02d}/{yy}")
        meses_entradas.append(round(e, 2))
        meses_saidas.append(round(s, 2))
        meses_investimentos.append(round(inv, 2))

    # gasto por pessoa (mês atual)
    pessoa_rows = db.execute(
        """SELECT u.display_name nome, u.color cor, COALESCE(SUM(t.valor),0) total
           FROM users u LEFT JOIN transactions t
             ON t.user_id = u.id AND t.tipo='saida' AND t.data >= ?
           GROUP BY u.id""",
        (month_start,),
    ).fetchall()

    ultimas = db.execute(
        """SELECT t.*, u.display_name nome FROM transactions t
           JOIN users u ON u.id = t.user_id
           ORDER BY t.data DESC, t.id DESC LIMIT 8"""
    ).fetchall()

    # contas fixas: total previsto no mês (para o comparativo fixas x entradas)
    competencia_atual = ensure_pagamentos_mes()
    fixas_mes_total = db.execute(
        "SELECT COALESCE(SUM(valor),0) t FROM pagamentos_fixos WHERE competencia = ?",
        (competencia_atual,),
    ).fetchone()["t"]

    # alertas de contas fixas: vencidas e a vencer nos próximos 7 dias
    vencidas, proximas = get_alertas_contas_fixas(7)
    fixas_vencidas_count = len(vencidas)
    fixas_vencidas_total = sum(r["valor"] for r, _ in vencidas)
    fixas_proximas_count = len(proximas)
    fixas_proximas_total = sum(r["valor"] for r, _ in proximas)
    fixas_proximas_nomes = ", ".join(r["descricao"] for r, _ in proximas[:4])

    return render_template(
        "dashboard.html",
        entradas_mes=entradas_mes,
        saidas_mes=saidas_mes,
        saldo_mes=saldo_mes,
        total_investido=total_investido,
        categorias_labels=json.dumps(categorias_labels),
        categorias_valores=json.dumps(categorias_valores),
        meses_labels=json.dumps(meses_labels),
        meses_entradas=json.dumps(meses_entradas),
        meses_saidas=json.dumps(meses_saidas),
        meses_investimentos=json.dumps(meses_investimentos),
        pessoa_rows=pessoa_rows,
        ultimas=ultimas,
        fixas_mes_total=fixas_mes_total,
        fixas_vencidas_count=fixas_vencidas_count,
        fixas_vencidas_total=fixas_vencidas_total,
        fixas_proximas_count=fixas_proximas_count,
        fixas_proximas_total=fixas_proximas_total,
        fixas_proximas_nomes=fixas_proximas_nomes,
    )


# ---------------------------------------------------------------------------
# Transações (entrada / saída manuais)
# ---------------------------------------------------------------------------

@app.route("/transacoes")
@login_required
def transacoes():
    db = get_db()
    tipo_filter = request.args.get("tipo", "")
    q = """SELECT t.*, u.display_name nome FROM transactions t
           JOIN users u ON u.id = t.user_id WHERE t.tipo NOT LIKE 'investimento%' """
    params = []
    if tipo_filter in ("entrada", "saida"):
        q += " AND t.tipo = ?"
        params.append(tipo_filter)
    q += " ORDER BY t.data DESC, t.id DESC"
    rows = db.execute(q, params).fetchall()
    return render_template("transactions.html", rows=rows, tipo_filter=tipo_filter, categorias=DEFAULT_CATEGORIES)


@app.route("/transacoes/nova", methods=["GET", "POST"])
@login_required
def nova_transacao():
    tipo = request.args.get("tipo", "saida")
    if request.method == "POST":
        db = get_db()
        tipo = request.form["tipo"]
        try:
            valor = parse_valor_brl(request.form["valor"])
        except ValueError:
            flash("Valor inválido. Use algo como 150,50.", "error")
            return render_template("transaction_form.html", tipo=tipo, categorias=DEFAULT_CATEGORIES, today=date.today().isoformat())
        data_str = request.form["data"]
        descricao = request.form["descricao"].strip()
        categoria = request.form.get("categoria", "").strip() or None
        comprovante_name = save_comprovante(request.files.get("comprovante"))
        db.execute(
            """INSERT INTO transactions (user_id, tipo, valor, data, descricao, categoria, origem, comprovante, criado_em)
               VALUES (?,?,?,?,?,?, 'manual', ?, ?)""",
            (session["user_id"], tipo, valor, data_str, descricao, categoria, comprovante_name, datetime.now().isoformat()),
        )
        db.commit()
        if categoria and tipo == "saida":
            learn_category(descricao, categoria)
        flash("Lançamento salvo!", "success")
        return redirect(url_for("transacoes"))
    return render_template("transaction_form.html", tipo=tipo, categorias=DEFAULT_CATEGORIES, today=date.today().isoformat())


@app.route("/transacoes/<int:tid>/excluir", methods=["POST"])
@login_required
def excluir_transacao(tid):
    db = get_db()
    db.execute("DELETE FROM transactions WHERE id = ?", (tid,))
    db.commit()
    flash("Lançamento excluído.", "success")
    return redirect(request.referrer or url_for("dashboard"))


# ---------------------------------------------------------------------------
# Contas fixas (recorrentes)
# ---------------------------------------------------------------------------

def ensure_pagamentos_mes(competencia=None):
    """Garante que toda conta fixa ativa tenha uma linha na competência (mês) informada."""
    db = get_db()
    if competencia is None:
        competencia = date.today().strftime("%Y-%m")
    contas = db.execute("SELECT * FROM contas_fixas WHERE ativo = 1").fetchall()
    for c in contas:
        existe = db.execute(
            "SELECT id FROM pagamentos_fixos WHERE conta_fixa_id = ? AND competencia = ?",
            (c["id"], competencia),
        ).fetchone()
        if not existe:
            db.execute(
                "INSERT INTO pagamentos_fixos (conta_fixa_id, competencia, valor, status) VALUES (?,?,?, 'pendente')",
                (c["id"], competencia, c["valor"]),
            )
    db.commit()
    return competencia


def due_date_for(competencia, dia):
    y, m = map(int, competencia.split("-"))
    last_day = calendar.monthrange(y, m)[1]
    d = min(int(dia), last_day)
    return date(y, m, d)


def get_alertas_contas_fixas(dias=7):
    """Retorna (vencidas, proximas) — listas de (linha, data_vencimento)."""
    db = get_db()
    today = date.today()
    limite = today + timedelta(days=dias)
    competencias = {today.strftime("%Y-%m")}
    if (limite.year, limite.month) != (today.year, today.month):
        competencias.add(limite.strftime("%Y-%m"))
    for comp in list(competencias):
        ensure_pagamentos_mes(comp)
    placeholders = ",".join("?" * len(competencias))
    rows = db.execute(
        f"""SELECT p.*, c.descricao, c.dia_vencimento FROM pagamentos_fixos p
            JOIN contas_fixas c ON c.id = p.conta_fixa_id
            WHERE p.status = 'pendente' AND p.competencia IN ({placeholders})""",
        tuple(competencias),
    ).fetchall()
    vencidas, proximas = [], []
    for r in rows:
        dv = due_date_for(r["competencia"], r["dia_vencimento"])
        if dv < today:
            vencidas.append((r, dv))
        elif dv <= limite:
            proximas.append((r, dv))
    vencidas.sort(key=lambda x: x[1])
    proximas.sort(key=lambda x: x[1])
    return vencidas, proximas


@app.route("/contas-fixas")
@login_required
def contas_fixas():
    competencia = ensure_pagamentos_mes()
    db = get_db()
    rows = db.execute(
        """SELECT p.*, c.descricao, c.dia_vencimento, c.responsavel, c.categoria AS categoria_padrao
           FROM pagamentos_fixos p JOIN contas_fixas c ON c.id = p.conta_fixa_id
           WHERE p.competencia = ? ORDER BY (p.status='pago'), c.dia_vencimento ASC""",
        (competencia,),
    ).fetchall()
    todas = db.execute("SELECT * FROM contas_fixas WHERE ativo = 1 ORDER BY descricao").fetchall()
    usuarios = db.execute("SELECT display_name FROM users ORDER BY display_name").fetchall()
    return render_template(
        "fixed_bills.html",
        rows=rows,
        todas=todas,
        competencia=competencia,
        categorias=DEFAULT_CATEGORIES,
        usuarios=usuarios,
        today=date.today().isoformat(),
    )


@app.route("/contas-fixas/nova", methods=["POST"])
@login_required
def nova_conta_fixa():
    db = get_db()
    descricao = request.form["descricao"].strip()
    try:
        valor = parse_valor_brl(request.form["valor"])
    except ValueError:
        flash("Valor inválido.", "error")
        return redirect(url_for("contas_fixas"))
    categoria = request.form.get("categoria", "").strip() or None
    responsavel = request.form.get("responsavel", "").strip() or None
    dia = max(1, min(31, int(request.form["dia_vencimento"])))
    db.execute(
        "INSERT INTO contas_fixas (descricao, valor, categoria, responsavel, dia_vencimento, ativo, criado_em) VALUES (?,?,?,?,?,1,?)",
        (descricao, valor, categoria, responsavel, dia, datetime.now().isoformat()),
    )
    db.commit()
    flash("Conta fixa cadastrada!", "success")
    return redirect(url_for("contas_fixas"))


@app.route("/contas-fixas/<int:cid>/desativar", methods=["POST"])
@login_required
def desativar_conta_fixa(cid):
    db = get_db()
    db.execute("UPDATE contas_fixas SET ativo = 0 WHERE id = ?", (cid,))
    db.commit()
    flash("Conta fixa removida da lista (o histórico de pagamentos é mantido).", "success")
    return redirect(url_for("contas_fixas"))


@app.route("/contas-fixas/pagar/<int:pid>", methods=["GET", "POST"])
@login_required
def pagar_conta_fixa(pid):
    db = get_db()
    pagamento = db.execute(
        """SELECT p.*, c.descricao, c.categoria AS categoria_padrao, c.responsavel
           FROM pagamentos_fixos p JOIN contas_fixas c ON c.id = p.conta_fixa_id
           WHERE p.id = ?""",
        (pid,),
    ).fetchone()
    if not pagamento:
        flash("Conta não encontrada.", "error")
        return redirect(url_for("contas_fixas"))

    if request.method == "POST":
        try:
            valor = parse_valor_brl(request.form["valor"])
        except ValueError:
            flash("Valor inválido.", "error")
            return redirect(url_for("pagar_conta_fixa", pid=pid))
        data_pagamento = request.form["data_pagamento"]
        categoria = request.form.get("categoria", "").strip() or pagamento["categoria_padrao"]
        comprovante_name = save_comprovante(request.files.get("comprovante"))

        cur = db.execute(
            """INSERT INTO transactions (user_id, tipo, valor, data, descricao, categoria, origem, comprovante, criado_em)
               VALUES (?, 'saida', ?, ?, ?, ?, 'conta_fixa', ?, ?)""",
            (session["user_id"], valor, data_pagamento, pagamento["descricao"], categoria,
             comprovante_name, datetime.now().isoformat()),
        )
        transaction_id = cur.lastrowid
        db.execute(
            """UPDATE pagamentos_fixos SET status='pago', data_pagamento=?, valor=?, comprovante=?, transaction_id=?
               WHERE id = ?""",
            (data_pagamento, valor, comprovante_name, transaction_id, pid),
        )
        db.commit()
        if categoria:
            learn_category(pagamento["descricao"], categoria)
        flash(f"Pagamento de \"{pagamento['descricao']}\" registrado nas saídas!", "success")
        return redirect(url_for("contas_fixas"))

    return render_template(
        "pay_fixed_bill.html",
        pagamento=pagamento,
        categorias=DEFAULT_CATEGORIES,
        today=date.today().isoformat(),
    )


@app.route("/contas-fixas/desfazer/<int:pid>", methods=["POST"])
@login_required
def desfazer_pagamento_fixo(pid):
    db = get_db()
    pag = db.execute("SELECT * FROM pagamentos_fixos WHERE id = ?", (pid,)).fetchone()
    if pag and pag["transaction_id"]:
        db.execute("DELETE FROM transactions WHERE id = ?", (pag["transaction_id"],))
    db.execute(
        "UPDATE pagamentos_fixos SET status='pendente', data_pagamento=NULL, transaction_id=NULL, comprovante=NULL WHERE id = ?",
        (pid,),
    )
    db.commit()
    flash("Pagamento desfeito — a conta voltou para pendente.", "success")
    return redirect(url_for("contas_fixas"))


# ---------------------------------------------------------------------------
# Investimentos (antigo "Futuro")
# ---------------------------------------------------------------------------

@app.route("/investimentos")
@login_required
def investimentos():
    db = get_db()
    instrumentos = db.execute("SELECT * FROM investimentos WHERE ativo = 1 ORDER BY nome").fetchall()
    totals = {}
    for inst in instrumentos:
        r = db.execute(
            """SELECT COALESCE(SUM(CASE WHEN tipo='investimento_deposito' THEN valor ELSE -valor END),0) t
               FROM transactions WHERE investimento_id = ?""",
            (inst["id"],),
        ).fetchone()
        totals[inst["id"]] = r["t"]
    total_geral = db.execute(
        "SELECT COALESCE(SUM(CASE WHEN tipo='investimento_deposito' THEN valor ELSE -valor END),0) t FROM transactions WHERE tipo LIKE 'investimento%'"
    ).fetchone()["t"]

    rows = db.execute(
        """SELECT t.*, u.display_name nome, i.nome AS investimento_nome FROM transactions t
           JOIN users u ON u.id = t.user_id
           LEFT JOIN investimentos i ON i.id = t.investimento_id
           WHERE t.tipo LIKE 'investimento%' ORDER BY t.data DESC, t.id DESC LIMIT 30"""
    ).fetchall()

    selic = fetch_taxa_bcb_cached(11)
    cdi = fetch_taxa_bcb_cached(12)

    return render_template(
        "investments.html",
        instrumentos=instrumentos,
        totals=totals,
        total_geral=total_geral,
        rows=rows,
        tipos=TIPOS_INVESTIMENTO,
        today=date.today().isoformat(),
        selic=selic,
        cdi=cdi,
    )


@app.route("/investimentos/novo", methods=["POST"])
@login_required
def novo_investimento():
    db = get_db()
    nome = request.form["nome"].strip()
    tipo = request.form.get("tipo", "Outro")
    if not nome:
        flash("Dê um nome para o investimento.", "error")
        return redirect(url_for("investimentos"))
    db.execute(
        "INSERT INTO investimentos (nome, tipo, ativo, criado_em) VALUES (?,?,1,?)",
        (nome, tipo, datetime.now().isoformat()),
    )
    db.commit()
    flash("Investimento cadastrado!", "success")
    return redirect(url_for("investimentos"))


@app.route("/investimentos/<int:iid>/desativar", methods=["POST"])
@login_required
def desativar_investimento(iid):
    db = get_db()
    db.execute("UPDATE investimentos SET ativo = 0 WHERE id = ?", (iid,))
    db.commit()
    flash("Investimento removido da lista (histórico mantido).", "success")
    return redirect(url_for("investimentos"))


@app.route("/investimentos/movimento", methods=["POST"])
@login_required
def movimento_investimento():
    db = get_db()
    investimento_id = request.form.get("investimento_id") or None
    acao = request.form["acao"]  # deposito | resgate
    tipo = "investimento_deposito" if acao == "deposito" else "investimento_resgate"
    try:
        valor = parse_valor_brl(request.form["valor"])
    except ValueError:
        flash("Valor inválido.", "error")
        return redirect(url_for("investimentos"))
    data_str = request.form["data"]
    descricao = request.form.get("descricao", "").strip() or ("Aporte" if acao == "deposito" else "Resgate")
    db.execute(
        """INSERT INTO transactions (user_id, tipo, valor, data, descricao, categoria, origem, investimento_id, criado_em)
           VALUES (?,?,?,?,?, 'Investimento', 'manual', ?, ?)""",
        (session["user_id"], tipo, valor, data_str, descricao, investimento_id, datetime.now().isoformat()),
    )
    db.commit()
    flash("Movimentação registrada!", "success")
    return redirect(url_for("investimentos"))


# ---------------------------------------------------------------------------
# Mural de sonhos (opcional, dentro de Investimentos)
# ---------------------------------------------------------------------------

@app.route("/sonhos")
@login_required
def sonhos():
    db = get_db()
    fotos = db.execute(
        """SELECT s.*, u.display_name nome FROM sonhos s JOIN users u ON u.id = s.user_id ORDER BY s.id DESC"""
    ).fetchall()
    return render_template("dreams.html", fotos=fotos)


@app.route("/sonhos/nova", methods=["POST"])
@login_required
def nova_sonho():
    db = get_db()
    fname = save_sonho(request.files.get("foto"))
    if not fname:
        flash("Envie uma imagem válida (jpg, png, webp ou gif).", "error")
        return redirect(url_for("sonhos"))
    legenda = request.form.get("legenda", "").strip()
    db.execute(
        "INSERT INTO sonhos (filename, legenda, user_id, criado_em) VALUES (?,?,?,?)",
        (fname, legenda, session["user_id"], datetime.now().isoformat()),
    )
    db.commit()
    flash("Foto adicionada ao mural de sonhos!", "success")
    return redirect(url_for("sonhos"))


@app.route("/sonhos/<int:sid>/excluir", methods=["POST"])
@login_required
def excluir_sonho(sid):
    db = get_db()
    db.execute("DELETE FROM sonhos WHERE id = ?", (sid,))
    db.commit()
    flash("Foto removida.", "success")
    return redirect(url_for("sonhos"))


# ---------------------------------------------------------------------------
# Previsão x Realizado
# ---------------------------------------------------------------------------

@app.route("/previsao")
@login_required
def previsao():
    db = get_db()
    today = date.today()
    y, m = today.year, today.month
    ms = []
    for i in range(5, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        ms.append((yy, mm))

    labels, planejado_gastos, planejado_ganhos, real_gastos, real_ganhos = [], [], [], [], []
    linhas_form = []
    for yy, mm in ms:
        comp = f"{yy:04d}-{mm:02d}"
        ini = f"{comp}-01"
        fim = f"{yy+1:04d}-01-01" if mm == 12 else f"{yy:04d}-{mm+1:02d}-01"
        prev = db.execute("SELECT * FROM previsoes_mensais WHERE competencia = ?", (comp,)).fetchone()
        pg = prev["planejado_gastos"] if prev else 0
        pgan = prev["planejado_ganhos"] if prev else 0
        rg = db.execute("SELECT COALESCE(SUM(valor),0) t FROM transactions WHERE tipo='saida' AND data>=? AND data<?", (ini, fim)).fetchone()["t"]
        rga = db.execute("SELECT COALESCE(SUM(valor),0) t FROM transactions WHERE tipo='entrada' AND data>=? AND data<?", (ini, fim)).fetchone()["t"]
        labels.append(f"{mm:02d}/{yy}")
        planejado_gastos.append(round(pg, 2))
        planejado_ganhos.append(round(pgan, 2))
        real_gastos.append(round(rg, 2))
        real_ganhos.append(round(rga, 2))
        linhas_form.append({"competencia": comp, "label": f"{mm:02d}/{yy}", "planejado_gastos": pg, "planejado_ganhos": pgan})

    return render_template(
        "forecast.html",
        labels=json.dumps(labels),
        planejado_gastos=json.dumps(planejado_gastos),
        planejado_ganhos=json.dumps(planejado_ganhos),
        real_gastos=json.dumps(real_gastos),
        real_ganhos=json.dumps(real_ganhos),
        linhas_form=linhas_form,
    )


@app.route("/previsao/salvar", methods=["POST"])
@login_required
def salvar_previsao():
    db = get_db()
    total_idx = int(request.form.get("total", 0))
    for i in range(total_idx):
        comp = request.form.get(f"competencia_{i}")
        if not comp:
            continue
        try:
            pg = parse_valor_brl(request.form.get(f"planejado_gastos_{i}") or "0")
            pgan = parse_valor_brl(request.form.get(f"planejado_ganhos_{i}") or "0")
        except ValueError:
            continue
        db.execute(
            """INSERT INTO previsoes_mensais (competencia, planejado_gastos, planejado_ganhos) VALUES (?,?,?)
               ON CONFLICT(competencia) DO UPDATE SET
                 planejado_gastos=excluded.planejado_gastos, planejado_ganhos=excluded.planejado_ganhos""",
            (comp, pg, pgan),
        )
    db.commit()
    flash("Previsões salvas!", "success")
    return redirect(url_for("previsao"))


# ---------------------------------------------------------------------------
# Importação de PDF
# ---------------------------------------------------------------------------

LINE_RE = re.compile(
    r"(?P<data>\d{2}[/.]\d{2}(?:[/.]\d{2,4})?)\s+(?P<desc>.+?)\s+"
    r"(?P<sinal>[-+])?\s?R?\$?\s?(?P<valor>(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2})\s*$"
)


def parse_pdf(filepath):
    candidatos = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                m = LINE_RE.search(line)
                if not m:
                    continue
                data_raw = m.group("data")
                desc = m.group("desc").strip()
                valor_raw = m.group("valor").replace(".", "").replace(",", ".")
                sinal = m.group("sinal")
                try:
                    valor = float(valor_raw)
                except ValueError:
                    continue
                if len(desc) < 3 or re.fullmatch(r"[\d\s./-]+", desc):
                    continue
                parts = re.split(r"[/.]", data_raw)
                if len(parts) == 2:
                    dia, mes = parts
                    ano = str(date.today().year)
                else:
                    dia, mes, ano = parts
                    if len(ano) == 2:
                        ano = "20" + ano
                try:
                    iso_data = f"{int(ano):04d}-{int(mes):02d}-{int(dia):02d}"
                    datetime.strptime(iso_data, "%Y-%m-%d")
                except ValueError:
                    continue
                tipo_sugerido = "entrada" if sinal == "+" else "saida"
                categoria_sugerida = guess_category(desc)
                candidatos.append(
                    {
                        "data": iso_data,
                        "descricao": desc,
                        "valor": abs(valor),
                        "tipo": tipo_sugerido,
                        "categoria": categoria_sugerida or "",
                    }
                )
    return candidatos


@app.route("/importar", methods=["GET", "POST"])
@login_required
def importar():
    if request.method == "POST":
        file = request.files.get("pdf")
        if not file or not file.filename.lower().endswith(".pdf"):
            flash("Envie um arquivo PDF válido.", "error")
            return redirect(url_for("importar"))
        tmp_path = os.path.join(BASE_DIR, f"_tmp_import_{uuid.uuid4().hex}.pdf")
        file.save(tmp_path)
        try:
            candidatos = parse_pdf(tmp_path)
        except Exception:
            flash("Não consegui ler esse PDF (pode estar protegido, digitalizado como imagem, ou corrompido). Tente lançar manualmente.", "error")
            candidatos = []
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        if not candidatos:
            flash("Não consegui identificar lançamentos nesse PDF. Você pode lançar manualmente.", "error")
            return redirect(url_for("importar"))
        session["import_candidatos"] = candidatos
        return redirect(url_for("importar_revisar"))
    return render_template("import.html")


@app.route("/importar/revisar", methods=["GET", "POST"])
@login_required
def importar_revisar():
    candidatos = session.get("import_candidatos", [])
    if not candidatos:
        flash("Não há uma importação pendente para revisar. Envie um PDF novamente.", "error")
        return redirect(url_for("importar"))

    if request.method == "POST":
        db = get_db()
        total_idx = int(request.form.get("total", 0))
        salvos = 0
        ignorados = 0
        for i in range(total_idx):
            if request.form.get(f"incluir_{i}") != "on":
                continue
            tipo = request.form.get(f"tipo_{i}")
            data_str = request.form.get(f"data_{i}", "").strip()
            descricao = request.form.get(f"descricao_{i}", "").strip()
            valor_raw = request.form.get(f"valor_{i}", "")
            categoria = request.form.get(f"categoria_{i}", "").strip() or None

            if tipo not in ("entrada", "saida") or not data_str or not descricao:
                ignorados += 1
                continue
            try:
                valor = parse_valor_brl(valor_raw)
                datetime.strptime(data_str, "%Y-%m-%d")
            except ValueError:
                ignorados += 1
                continue

            db.execute(
                """INSERT INTO transactions (user_id, tipo, valor, data, descricao, categoria, origem, criado_em)
                   VALUES (?,?,?,?,?,?, 'pdf', ?)""",
                (session["user_id"], tipo, valor, data_str, descricao, categoria, datetime.now().isoformat()),
            )
            if categoria and tipo == "saida":
                learn_category(descricao, categoria)
            salvos += 1
        db.commit()
        session.pop("import_candidatos", None)
        msg = f"{salvos} lançamento(s) importado(s) com sucesso!"
        if ignorados:
            msg += f" {ignorados} linha(s) foram ignoradas por terem data/valor inválido."
        flash(msg, "success" if salvos else "error")
        return redirect(url_for("dashboard") if salvos else url_for("importar"))

    return render_template("import_review.html", candidatos=candidatos, categorias=DEFAULT_CATEGORIES)


if __name__ == "__main__":
    init_db()
    print("\n== Finanças da Casa ==")
    print("Neste computador: http://127.0.0.1:5000")
    print("Em outros aparelhos da mesma rede Wi-Fi: http://SEU-IP-LOCAL:5000")
    print("(veja no README como descobrir o SEU-IP-LOCAL)\n")
    app.run(host="0.0.0.0", debug=False, port=5000)
