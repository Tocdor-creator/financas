"""Caixinhas: dinheiro guardado por objetivo, com foto e meta opcionais.

No banco, as caixinhas ficam na tabela `investimentos` e os movimentos em `transactions`
com tipo `investimento_deposito` (guardar) ou `investimento_resgate` (resgatar).
"""
from datetime import date, datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import taxas
from .arquivos import salvar_foto
from .auth import login_required
from .config import TIPOS_CAIXINHA
from .db import get_db
from .formatacao import formatar_brl, parse_valor

bp = Blueprint("caixinhas", __name__, url_prefix="/caixinhas")

DEPOSITO = "investimento_deposito"
RESGATE = "investimento_resgate"
TOLERANCIA = 0.005  # margem para comparar valores em reais armazenados como float


def efeito_no_saldo(tipo, valor):
    return valor if tipo == DEPOSITO else -valor


_SOMA_SALDO = "COALESCE(SUM(CASE WHEN tipo = ? THEN valor WHEN tipo = ? THEN -valor END), 0)"


def saldo(db, caixinha_id):
    return db.execute(
        f"SELECT {_SOMA_SALDO} FROM transactions WHERE investimento_id = ?", (DEPOSITO, RESGATE, caixinha_id)
    ).fetchone()[0]


def total_guardado(db):
    return db.execute(f"SELECT {_SOMA_SALDO} FROM transactions", (DEPOSITO, RESGATE)).fetchone()[0]


def listar(db):
    """Caixinhas ativas com saldo e progresso da meta (0-100, ou None sem meta)."""
    linhas = db.execute(
        """SELECT i.*, COALESCE(SUM(CASE WHEN t.tipo = ? THEN t.valor WHEN t.tipo = ? THEN -t.valor END), 0) AS saldo
           FROM investimentos i LEFT JOIN transactions t ON t.investimento_id = i.id
           WHERE i.ativo = 1 GROUP BY i.id ORDER BY i.nome""",
        (DEPOSITO, RESGATE),
    ).fetchall()
    caixinhas = []
    for linha in linhas:
        caixinha = dict(linha)
        meta = caixinha["meta"]
        caixinha["progresso"] = max(0, min(100, round(caixinha["saldo"] / meta * 100))) if meta else None
        caixinhas.append(caixinha)
    return caixinhas


def _ler_meta(texto):
    """Meta é opcional: vazio ou zero viram None. Lança ValueError se inválida."""
    if not (texto or "").strip():
        return None
    return parse_valor(texto) or None


@bp.route("/")
@login_required
def lista():
    db = get_db()
    return render_template(
        "caixinhas/lista.html",
        caixinhas=listar(db),
        total=total_guardado(db),
        tipos=TIPOS_CAIXINHA,
        selic=taxas.taxa(taxas.SERIE_SELIC),
        cdi=taxas.taxa(taxas.SERIE_CDI),
    )


@bp.route("/nova", methods=["POST"])
@login_required
def nova():
    nome = request.form.get("nome", "").strip()
    try:
        meta = _ler_meta(request.form.get("meta"))
    except ValueError:
        flash("Meta inválida. Use algo como 5.000,00.", "error")
        return redirect(url_for("caixinhas.lista"))
    if not nome:
        flash("Dê um nome para a caixinha.", "error")
        return redirect(url_for("caixinhas.lista"))

    db = get_db()
    cursor = db.execute(
        "INSERT INTO investimentos (nome, tipo, meta, foto, ativo, criado_em) VALUES (?, ?, ?, ?, 1, ?)",
        (nome, request.form.get("tipo", "Outro"), meta, salvar_foto(request.files.get("foto")), datetime.now().isoformat()),
    )
    db.commit()
    flash(f"Caixinha {nome} criada.", "success")
    return redirect(url_for("caixinhas.detalhe", caixinha_id=cursor.lastrowid))


@bp.route("/<int:caixinha_id>")
@login_required
def detalhe(caixinha_id):
    db = get_db()
    caixinha = next((c for c in listar(db) if c["id"] == caixinha_id), None)
    if not caixinha:
        flash("Caixinha não encontrada.", "error")
        return redirect(url_for("caixinhas.lista"))
    movimentos = db.execute(
        """SELECT t.*, u.display_name AS nome FROM transactions t JOIN users u ON u.id = t.user_id
           WHERE t.investimento_id = ? ORDER BY t.data DESC, t.id DESC""",
        (caixinha_id,),
    ).fetchall()
    return render_template(
        "caixinhas/detalhe.html",
        caixinha=caixinha,
        movimentos=movimentos,
        tipos=TIPOS_CAIXINHA,
        hoje=date.today().isoformat(),
    )


@bp.route("/<int:caixinha_id>/editar", methods=["POST"])
@login_required
def editar(caixinha_id):
    nome = request.form.get("nome", "").strip()
    try:
        meta = _ler_meta(request.form.get("meta"))
    except ValueError:
        flash("Meta inválida. Use algo como 5.000,00.", "error")
        return redirect(url_for("caixinhas.detalhe", caixinha_id=caixinha_id))
    if not nome:
        flash("Dê um nome para a caixinha.", "error")
        return redirect(url_for("caixinhas.detalhe", caixinha_id=caixinha_id))

    db = get_db()
    db.execute(
        "UPDATE investimentos SET nome = ?, tipo = ?, meta = ? WHERE id = ?",
        (nome, request.form.get("tipo", "Outro"), meta, caixinha_id),
    )
    foto = salvar_foto(request.files.get("foto"))
    if foto:
        db.execute("UPDATE investimentos SET foto = ? WHERE id = ?", (foto, caixinha_id))
    db.commit()
    flash("Caixinha atualizada.", "success")
    return redirect(url_for("caixinhas.detalhe", caixinha_id=caixinha_id))


@bp.route("/<int:caixinha_id>/apagar", methods=["POST"])
@login_required
def apagar(caixinha_id):
    db = get_db()
    restante = saldo(db, caixinha_id)
    if abs(restante) > TOLERANCIA:
        flash(f"A caixinha ainda tem {formatar_brl(restante)}. Resgate o valor antes de apagar.", "error")
        return redirect(url_for("caixinhas.detalhe", caixinha_id=caixinha_id))
    db.execute("UPDATE investimentos SET ativo = 0 WHERE id = ?", (caixinha_id,))
    db.commit()
    flash("Caixinha apagada. As movimentações continuam no histórico.", "success")
    return redirect(url_for("caixinhas.lista"))


@bp.route("/<int:caixinha_id>/movimentar", methods=["POST"])
@login_required
def movimentar(caixinha_id):
    db = get_db()
    caixinha = db.execute("SELECT * FROM investimentos WHERE id = ? AND ativo = 1", (caixinha_id,)).fetchone()
    if not caixinha:
        flash("Caixinha não encontrada.", "error")
        return redirect(url_for("caixinhas.lista"))

    voltar = redirect(url_for("caixinhas.detalhe", caixinha_id=caixinha_id))
    guardar = request.form.get("acao") == "guardar"
    try:
        valor = parse_valor(request.form.get("valor"))
        data = date.fromisoformat(request.form.get("data") or date.today().isoformat()).isoformat()
    except ValueError:
        flash("Confira o valor e a data.", "error")
        return voltar
    if valor <= 0:
        flash("O valor precisa ser maior que zero.", "error")
        return voltar
    disponivel = saldo(db, caixinha_id)
    if not guardar and valor > disponivel + TOLERANCIA:
        flash(f"A caixinha só tem {formatar_brl(disponivel)} para resgatar.", "error")
        return voltar

    descricao = request.form.get("descricao", "").strip() or (
        f"Guardado em {caixinha['nome']}" if guardar else f"Resgate de {caixinha['nome']}"
    )
    db.execute(
        """INSERT INTO transactions (user_id, tipo, valor, data, descricao, categoria, origem, investimento_id, criado_em)
           VALUES (?, ?, ?, ?, ?, 'Investimento', 'manual', ?, ?)""",
        (
            g.user["id"],
            DEPOSITO if guardar else RESGATE,
            valor,
            data,
            descricao,
            caixinha_id,
            datetime.now().isoformat(),
        ),
    )
    db.commit()
    flash(f"{formatar_brl(valor)} {'guardado' if guardar else 'resgatado'}.", "success")
    return voltar
