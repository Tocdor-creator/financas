"""Extrato e cadastro/edição de lançamentos (entradas, saídas e movimentos de caixinha)."""
from datetime import date, datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import caixinhas, categorias
from .arquivos import salvar_comprovante
from .auth import login_required
from .config import CATEGORIAS
from .contas import reabrir_pagamento_do_lancamento
from .db import get_db
from .formatacao import deslocar_mes, limites_mes, nome_mes, parse_valor

bp = Blueprint("lancamentos", __name__)

TIPOS_MANUAIS = ("entrada", "saida")
FILTROS = {"entrada": "t.tipo = 'entrada'", "saida": "t.tipo = 'saida'", "caixinha": "t.tipo LIKE 'investimento%'"}


def _url_retorno(padrao):
    """Destino após salvar/excluir, vindo do parâmetro `voltar`. Só aceita caminhos internos."""
    destino = request.values.get("voltar", "")
    return destino if destino.startswith("/") and not destino.startswith("//") else padrao


def _mes_da_query():
    hoje = date.today()
    try:
        ano, mes = map(int, request.args.get("mes", "").split("-"))
        date(ano, mes, 1)
    except ValueError:
        return hoje.year, hoje.month
    return ano, mes


def buscar(db, lancamento_id):
    return db.execute(
        """SELECT t.*, u.display_name AS nome, i.nome AS caixinha_nome, c.descricao AS conta_fixa_nome
           FROM transactions t
           JOIN users u ON u.id = t.user_id
           LEFT JOIN investimentos i ON i.id = t.investimento_id
           LEFT JOIN pagamentos_fixos p ON p.transaction_id = t.id
           LEFT JOIN contas_fixas c ON c.id = p.conta_fixa_id
           WHERE t.id = ?""",
        (lancamento_id,),
    ).fetchone()


def ultimos(db, limite):
    return db.execute(
        """SELECT t.*, u.display_name AS nome, i.nome AS caixinha_nome FROM transactions t
           JOIN users u ON u.id = t.user_id
           LEFT JOIN investimentos i ON i.id = t.investimento_id
           ORDER BY t.data DESC, t.id DESC LIMIT ?""",
        (limite,),
    ).fetchall()


def soma(db, tipo, inicio=None, fim=None):
    sql, params = "SELECT COALESCE(SUM(valor), 0) FROM transactions WHERE tipo = ?", [tipo]
    if inicio:
        sql += " AND data >= ? AND data < ?"
        params += [inicio, fim]
    return db.execute(sql, params).fetchone()[0]


@bp.route("/extrato")
@login_required
def extrato():
    db = get_db()
    filtro = request.args.get("tipo", "")
    ano, mes = _mes_da_query()
    inicio, fim = limites_mes(ano, mes)

    sql = """SELECT t.*, u.display_name AS nome, i.nome AS caixinha_nome FROM transactions t
             JOIN users u ON u.id = t.user_id
             LEFT JOIN investimentos i ON i.id = t.investimento_id
             WHERE t.data >= ? AND t.data < ?"""
    if filtro in FILTROS:
        sql += f" AND {FILTROS[filtro]}"
    linhas = db.execute(sql + " ORDER BY t.data DESC, t.id DESC", (inicio, fim)).fetchall()

    dias = []
    for linha in linhas:
        if not dias or dias[-1][0] != linha["data"]:
            dias.append((linha["data"], []))
        dias[-1][1].append(linha)

    return render_template(
        "lancamentos/extrato.html",
        dias=dias,
        filtro=filtro,
        mes=f"{ano:04d}-{mes:02d}",
        mes_nome=nome_mes(ano, mes),
        mes_anterior="{:04d}-{:02d}".format(*deslocar_mes(ano, mes, -1)),
        mes_seguinte="{:04d}-{:02d}".format(*deslocar_mes(ano, mes, 1)),
        entradas=soma(db, "entrada", inicio, fim),
        saidas=soma(db, "saida", inicio, fim),
    )


@bp.route("/lancamentos/novo", methods=["GET", "POST"])
@login_required
def novo():
    tipo = request.values.get("tipo")
    if tipo not in TIPOS_MANUAIS:
        tipo = "saida"
    contexto = {"tipo": tipo, "categorias": CATEGORIAS, "hoje": date.today().isoformat()}
    if request.method == "GET":
        return render_template("lancamentos/novo.html", **contexto)

    descricao = request.form.get("descricao", "").strip()
    try:
        valor = parse_valor(request.form.get("valor"))
        data = date.fromisoformat(request.form.get("data", "")).isoformat()
    except ValueError:
        flash("Confira o valor e a data. Exemplo de valor: 150,50.", "error")
        return render_template("lancamentos/novo.html", **contexto)
    if not descricao:
        flash("Informe uma descrição.", "error")
        return render_template("lancamentos/novo.html", **contexto)

    categoria = request.form.get("categoria", "").strip() or None
    db = get_db()
    db.execute(
        """INSERT INTO transactions (user_id, tipo, valor, data, descricao, categoria, origem, comprovante, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, ?)""",
        (g.user["id"], tipo, valor, data, descricao, categoria,
         salvar_comprovante(request.files.get("comprovante")), datetime.now().isoformat()),
    )
    db.commit()
    if tipo == "saida":
        categorias.aprender(db, descricao, categoria)
    flash("Lançamento salvo.", "success")
    return redirect(url_for("lancamentos.extrato", mes=data[:7]))


def _validar_edicao(lancamento, form):
    """Lê o formulário de edição. Retorna (dados, None) ou (None, mensagem de erro)."""
    try:
        valor = parse_valor(form.get("valor"))
        data = date.fromisoformat(form.get("data", "")).isoformat()
    except ValueError:
        return None, "Confira o valor e a data. Exemplo de valor: 150,50."
    descricao = form.get("descricao", "").strip()
    if valor <= 0 or not descricao:
        return None, "Informe um valor maior que zero e uma descrição."

    eh_caixinha = lancamento["tipo"] in (caixinhas.DEPOSITO, caixinhas.RESGATE)
    tipo = lancamento["tipo"]
    # Movimento de caixinha mantém o tipo; pagamento de conta fixa é sempre saída.
    if not eh_caixinha and lancamento["origem"] != "conta_fixa" and form.get("tipo") in TIPOS_MANUAIS:
        tipo = form["tipo"]
    categoria = "Investimento" if eh_caixinha else (form.get("categoria", "").strip() or None)
    return {"tipo": tipo, "valor": valor, "data": data, "descricao": descricao, "categoria": categoria}, None


@bp.route("/lancamentos/<int:lancamento_id>/editar", methods=["GET", "POST"])
@login_required
def editar(lancamento_id):
    db = get_db()
    lancamento = buscar(db, lancamento_id)
    if not lancamento:
        flash("Lançamento não encontrado.", "error")
        return redirect(url_for("lancamentos.extrato"))
    voltar = _url_retorno(url_for("lancamentos.extrato", mes=lancamento["data"][:7]))
    eh_caixinha = lancamento["tipo"] in (caixinhas.DEPOSITO, caixinhas.RESGATE)

    if request.method == "GET":
        return render_template(
            "lancamentos/editar.html", lancamento=lancamento, eh_caixinha=eh_caixinha, voltar=voltar, categorias=CATEGORIAS
        )

    dados, erro = _validar_edicao(lancamento, request.form)
    if not erro and eh_caixinha:
        saldo_final = (
            caixinhas.saldo(db, lancamento["investimento_id"])
            - caixinhas.efeito_no_saldo(lancamento["tipo"], lancamento["valor"])
            + caixinhas.efeito_no_saldo(dados["tipo"], dados["valor"])
        )
        if saldo_final < -caixinhas.TOLERANCIA:
            erro = "Com esse valor a caixinha ficaria negativa."
    if erro:
        flash(erro, "error")
        return redirect(url_for("lancamentos.editar", lancamento_id=lancamento_id, voltar=voltar))

    comprovante = salvar_comprovante(request.files.get("comprovante"))
    if not comprovante and request.form.get("remover_comprovante") != "on":
        comprovante = lancamento["comprovante"]

    db.execute(
        "UPDATE transactions SET tipo = ?, valor = ?, data = ?, descricao = ?, categoria = ?, comprovante = ? WHERE id = ?",
        (dados["tipo"], dados["valor"], dados["data"], dados["descricao"], dados["categoria"], comprovante, lancamento_id),
    )
    # Se for pagamento de conta fixa, a conta acompanha valor, data e comprovante.
    db.execute(
        "UPDATE pagamentos_fixos SET valor = ?, data_pagamento = ?, comprovante = ? WHERE transaction_id = ?",
        (dados["valor"], dados["data"], comprovante, lancamento_id),
    )
    db.commit()
    if dados["tipo"] == "saida":
        categorias.aprender(db, dados["descricao"], dados["categoria"])
    flash("Lançamento atualizado.", "success")
    return redirect(voltar)


@bp.route("/lancamentos/<int:lancamento_id>/excluir", methods=["POST"])
@login_required
def excluir(lancamento_id):
    db = get_db()
    voltar = _url_retorno(url_for("lancamentos.extrato"))
    lancamento = db.execute("SELECT * FROM transactions WHERE id = ?", (lancamento_id,)).fetchone()
    if not lancamento:
        flash("Lançamento não encontrado.", "error")
        return redirect(voltar)
    if (lancamento["tipo"] == caixinhas.DEPOSITO
            and caixinhas.saldo(db, lancamento["investimento_id"]) - lancamento["valor"] < -caixinhas.TOLERANCIA):
        flash("Parte desse dinheiro já foi resgatada; excluir deixaria a caixinha negativa.", "error")
        return redirect(voltar)

    db.execute("DELETE FROM transactions WHERE id = ?", (lancamento_id,))
    reabrir_pagamento_do_lancamento(db, lancamento_id)
    db.commit()
    flash("Lançamento excluído.", "success")
    return redirect(voltar)
