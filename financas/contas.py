"""Contas fixas: cadastradas uma vez, geram um pagamento pendente por mês."""
from datetime import date, datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import categorias
from .arquivos import salvar_comprovante
from .auth import login_required
from .config import CATEGORIAS
from .db import get_db
from .formatacao import data_curta, nome_mes, parse_valor, vencimento

bp = Blueprint("contas", __name__, url_prefix="/contas")

DIAS_AVISO_VENCIMENTO = 7


def competencia_atual():
    return date.today().strftime("%Y-%m")


def gerar_pagamentos(db, competencia):
    """Garante uma linha em pagamentos_fixos para cada conta ativa na competência (YYYY-MM)."""
    db.execute(
        """INSERT OR IGNORE INTO pagamentos_fixos (conta_fixa_id, competencia, valor, status)
           SELECT id, ?, valor, 'pendente' FROM contas_fixas WHERE ativo = 1""",
        (competencia,),
    )
    db.commit()


def _situacao(pagamento, venc, hoje):
    if pagamento["status"] == "pago":
        return "paga", f"Paga em {data_curta(pagamento['data_pagamento'])}"
    dias = (venc - hoje).days
    if dias < 0:
        return "vencida", f"Venceu {data_curta(venc)}"
    if dias == 0:
        return "hoje", "Vence hoje"
    if dias <= DIAS_AVISO_VENCIMENTO:
        return "breve", f"Vence em {dias} dia{'s' if dias > 1 else ''}"
    return "futura", f"Vence {data_curta(venc)}"


def contas_do_mes(db, competencia):
    """Pagamentos da competência mais os pendentes de meses anteriores, com vencimento e situação."""
    gerar_pagamentos(db, competencia)
    linhas = db.execute(
        """SELECT p.*, c.descricao, c.dia_vencimento, c.responsavel, c.categoria
           FROM pagamentos_fixos p JOIN contas_fixas c ON c.id = p.conta_fixa_id
           WHERE p.competencia = ? OR (p.status = 'pendente' AND p.competencia < ? AND c.ativo = 1)
           ORDER BY p.status = 'pago', p.competencia, c.dia_vencimento""",
        (competencia, competencia),
    ).fetchall()
    hoje = date.today()
    contas = []
    for linha in linhas:
        conta = dict(linha)
        conta["vencimento"] = vencimento(linha["competencia"], linha["dia_vencimento"])
        conta["situacao"], conta["situacao_texto"] = _situacao(linha, conta["vencimento"], hoje)
        contas.append(conta)
    return contas


def resumo(contas):
    pendentes = [c for c in contas if c["status"] != "pago"]
    return {
        "pendentes": pendentes,
        "a_pagar": sum(c["valor"] for c in pendentes),
        "pago": sum(c["valor"] for c in contas if c["status"] == "pago"),
        "pagas": len(contas) - len(pendentes),
        "total": len(contas),
    }


@bp.route("/")
@login_required
def lista():
    db = get_db()
    competencia = competencia_atual()
    contas = contas_do_mes(db, competencia)
    ano, mes = map(int, competencia.split("-"))
    return render_template(
        "contas/lista.html",
        contas=contas,
        resumo=resumo(contas),
        cadastradas=db.execute("SELECT * FROM contas_fixas WHERE ativo = 1 ORDER BY descricao").fetchall(),
        usuarios=db.execute("SELECT display_name FROM users ORDER BY display_name").fetchall(),
        mes=nome_mes(ano, mes),
        categorias=CATEGORIAS,
    )


@bp.route("/nova", methods=["POST"])
@login_required
def nova():
    descricao = request.form.get("descricao", "").strip()
    try:
        valor = parse_valor(request.form.get("valor"))
        dia = int(request.form.get("dia_vencimento", ""))
    except ValueError:
        flash("Confira o valor e o dia de vencimento (1 a 31).", "error")
        return redirect(url_for("contas.lista"))
    if not descricao:
        flash("Informe o nome da conta.", "error")
        return redirect(url_for("contas.lista"))

    db = get_db()
    db.execute(
        "INSERT INTO contas_fixas (descricao, valor, categoria, responsavel, dia_vencimento, ativo, criado_em) "
        "VALUES (?, ?, ?, ?, ?, 1, ?)",
        (
            descricao,
            valor,
            request.form.get("categoria", "").strip() or None,
            request.form.get("responsavel", "").strip() or None,
            max(1, min(31, dia)),
            datetime.now().isoformat(),
        ),
    )
    db.commit()
    flash("Conta cadastrada.", "success")
    return redirect(url_for("contas.lista"))


@bp.route("/<int:conta_id>/remover", methods=["POST"])
@login_required
def remover(conta_id):
    db = get_db()
    db.execute("UPDATE contas_fixas SET ativo = 0 WHERE id = ?", (conta_id,))
    # Pagamentos já feitos continuam no histórico; só as pendências deixam de existir.
    db.execute("DELETE FROM pagamentos_fixos WHERE conta_fixa_id = ? AND status = 'pendente'", (conta_id,))
    db.commit()
    flash("Conta removida. Os pagamentos anteriores continuam no histórico.", "success")
    return redirect(url_for("contas.lista"))


@bp.route("/pagamentos/<int:pagamento_id>/pagar", methods=["GET", "POST"])
@login_required
def pagar(pagamento_id):
    db = get_db()
    pagamento = db.execute(
        """SELECT p.*, c.descricao, c.categoria, c.responsavel
           FROM pagamentos_fixos p JOIN contas_fixas c ON c.id = p.conta_fixa_id
           WHERE p.id = ?""",
        (pagamento_id,),
    ).fetchone()
    if not pagamento:
        flash("Conta não encontrada.", "error")
        return redirect(url_for("contas.lista"))

    if request.method == "POST":
        try:
            valor = parse_valor(request.form.get("valor"))
            data_pagamento = date.fromisoformat(request.form.get("data_pagamento", "")).isoformat()
        except ValueError:
            flash("Confira o valor e a data do pagamento.", "error")
            return redirect(url_for("contas.pagar", pagamento_id=pagamento_id))
        categoria = request.form.get("categoria", "").strip() or pagamento["categoria"]
        comprovante = salvar_comprovante(request.files.get("comprovante"))

        cursor = db.execute(
            """INSERT INTO transactions (user_id, tipo, valor, data, descricao, categoria, origem, comprovante, criado_em)
               VALUES (?, 'saida', ?, ?, ?, ?, 'conta_fixa', ?, ?)""",
            (g.user["id"], valor, data_pagamento, pagamento["descricao"], categoria, comprovante, datetime.now().isoformat()),
        )
        db.execute(
            "UPDATE pagamentos_fixos SET status = 'pago', data_pagamento = ?, valor = ?, comprovante = ?, transaction_id = ? "
            "WHERE id = ?",
            (data_pagamento, valor, comprovante, cursor.lastrowid, pagamento_id),
        )
        db.commit()
        categorias.aprender(db, pagamento["descricao"], categoria)
        flash(f"Pagamento de {pagamento['descricao']} registrado.", "success")
        return redirect(url_for("contas.lista"))

    return render_template("contas/pagar.html", pagamento=pagamento, categorias=CATEGORIAS, hoje=date.today().isoformat())


@bp.route("/pagamentos/<int:pagamento_id>/desfazer", methods=["POST"])
@login_required
def desfazer(pagamento_id):
    db = get_db()
    pagamento = db.execute("SELECT transaction_id FROM pagamentos_fixos WHERE id = ?", (pagamento_id,)).fetchone()
    if pagamento and pagamento["transaction_id"]:
        db.execute("DELETE FROM transactions WHERE id = ?", (pagamento["transaction_id"],))
    reabrir_pagamento(db, pagamento_id)
    db.commit()
    flash("Pagamento desfeito. A conta voltou a ficar pendente.", "success")
    return redirect(url_for("contas.lista"))


_REABRIR = (
    "UPDATE pagamentos_fixos SET status = 'pendente', data_pagamento = NULL, transaction_id = NULL, comprovante = NULL "
)


def reabrir_pagamento(db, pagamento_id):
    db.execute(_REABRIR + "WHERE id = ?", (pagamento_id,))


def reabrir_pagamento_do_lancamento(db, lancamento_id):
    """Quando o lançamento de um pagamento é excluído, a conta volta a ficar pendente."""
    db.execute(_REABRIR + "WHERE transaction_id = ?", (lancamento_id,))
