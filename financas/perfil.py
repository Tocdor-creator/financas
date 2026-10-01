from datetime import date

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, send_file, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import login_required
from .config import TEMA_PADRAO, TEMAS
from .db import get_db

bp = Blueprint("perfil", __name__, url_prefix="/perfil")

TAMANHO_MINIMO_SENHA = 4


@bp.app_context_processor
def tema_do_usuario():
    chave = g.user["tema"] if g.get("user") and g.user["tema"] in TEMAS else TEMA_PADRAO
    return {"tema": TEMAS[chave], "tema_chave": chave}


@bp.route("/")
@login_required
def index():
    return render_template("perfil/index.html", temas=TEMAS)


@bp.route("/senha", methods=["POST"])
@login_required
def trocar_senha():
    atual = request.form.get("senha_atual", "")
    nova = request.form.get("senha_nova", "")
    if not check_password_hash(g.user["password_hash"], atual):
        flash("Senha atual incorreta.", "error")
    elif len(nova) < TAMANHO_MINIMO_SENHA:
        flash(f"A nova senha deve ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.", "error")
    elif nova != request.form.get("senha_confirmar", ""):
        flash("A confirmação não confere com a nova senha.", "error")
    else:
        db = get_db()
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(nova), g.user["id"]))
        db.commit()
        flash("Senha atualizada.", "success")
    return redirect(url_for("perfil.index"))


@bp.route("/aparencia", methods=["POST"])
@login_required
def salvar_aparencia():
    tema = request.form.get("tema")
    if tema not in TEMAS:
        tema = TEMA_PADRAO
    db = get_db()
    db.execute("UPDATE users SET tema = ? WHERE id = ?", (tema, g.user["id"]))
    db.commit()
    flash("Aparência atualizada.", "success")
    return redirect(url_for("perfil.index"))


@bp.route("/backup")
@login_required
def backup():
    return send_file(
        current_app.config["DATABASE"],
        as_attachment=True,
        download_name=f"financas_backup_{date.today().isoformat()}.db",
    )
