from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .config import BLOQUEIO_MINUTOS, MAX_TENTATIVAS_LOGIN
from .db import get_db

bp = Blueprint("auth", __name__)

CORES_USUARIOS = ["#820ad1", "#0a8754"]


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper


def _existe_usuario():
    return get_db().execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


@bp.before_app_request
def carregar_usuario():
    user_id = session.get("user_id")
    g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone() if user_id else None


@bp.before_app_request
def exigir_configuracao_inicial():
    if request.endpoint not in ("auth.configurar", "static") and not _existe_usuario():
        return redirect(url_for("auth.configurar"))


# --- limite de tentativas de login -------------------------------------------

def _tentativa(username):
    return get_db().execute("SELECT * FROM login_attempts WHERE username = ?", (username,)).fetchone()


def _limpar_tentativas(username):
    db = get_db()
    db.execute("DELETE FROM login_attempts WHERE username = ?", (username,))
    db.commit()


def _registrar_falha(username):
    """Conta a falha; ao atingir o limite, bloqueia o usuário por BLOQUEIO_MINUTOS. Retorna o registro atualizado."""
    db = get_db()
    atual = _tentativa(username)
    tentativas = (atual["tentativas"] if atual else 0) + 1
    bloqueado_ate = atual["bloqueado_ate"] if atual else None
    if tentativas >= MAX_TENTATIVAS_LOGIN:
        tentativas = 0
        bloqueado_ate = (datetime.now() + timedelta(minutes=BLOQUEIO_MINUTOS)).isoformat()
    db.execute(
        "INSERT INTO login_attempts (username, tentativas, bloqueado_ate) VALUES (?, ?, ?) "
        "ON CONFLICT (username) DO UPDATE SET tentativas = excluded.tentativas, bloqueado_ate = excluded.bloqueado_ate",
        (username, tentativas, bloqueado_ate),
    )
    db.commit()
    return tentativas, bloqueado_ate


def _bloqueado_ate(username):
    registro = _tentativa(username)
    if not registro or not registro["bloqueado_ate"]:
        return None
    fim = datetime.fromisoformat(registro["bloqueado_ate"])
    if datetime.now() < fim:
        return fim
    _limpar_tentativas(username)
    return None


# --- rotas -------------------------------------------------------------------

@bp.route("/configurar", methods=["GET", "POST"])
def configurar():
    if _existe_usuario():
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        db = get_db()
        for i, cor in enumerate(CORES_USUARIOS, start=1):
            username = request.form.get(f"username{i}", "").strip().lower()
            nome = request.form.get(f"display{i}", "").strip()
            senha = request.form.get(f"password{i}", "")
            if username and nome and senha:
                db.execute(
                    "INSERT INTO users (username, display_name, password_hash, color) VALUES (?, ?, ?, ?)",
                    (username, nome, generate_password_hash(senha), cor),
                )
        db.commit()
        flash("Contas criadas. Agora é só entrar.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/configurar.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("inicio.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        senha = request.form.get("password", "")

        bloqueio = _bloqueado_ate(username)
        if bloqueio:
            flash(f"Muitas tentativas erradas. Tente novamente após {bloqueio:%H:%M}.", "error")
            return render_template("auth/login.html")

        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], senha):
            _limpar_tentativas(username)
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("inicio.index"))

        tentativas, bloqueado_ate = _registrar_falha(username)
        if bloqueado_ate and tentativas == 0:
            flash(f"Muitas tentativas erradas. Login bloqueado por {BLOQUEIO_MINUTOS} minutos.", "error")
        else:
            flash(f"Usuário ou senha incorretos. Tentativas restantes: {MAX_TENTATIVAS_LOGIN - tentativas}.", "error")
    return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
