from datetime import date

from flask import Blueprint, render_template

from . import caixinhas
from .auth import login_required
from .contas import competencia_atual, contas_do_mes, resumo
from .db import get_db
from .formatacao import MESES, limites_mes, rotulo_mes_curto, ultimos_meses
from .lancamentos import soma, ultimos

bp = Blueprint("inicio", __name__)


def _gastos_por_categoria(db, inicio, fim, total):
    linhas = db.execute(
        """SELECT COALESCE(categoria, 'Outros') AS nome, SUM(valor) AS total
           FROM transactions WHERE tipo = 'saida' AND data >= ? AND data < ?
           GROUP BY COALESCE(categoria, 'Outros') ORDER BY total DESC""",
        (inicio, fim),
    ).fetchall()
    return [
        {"nome": linha["nome"], "total": linha["total"], "pct": round(linha["total"] / total * 100) if total else 0}
        for linha in linhas
    ]


def _gastos_por_pessoa(db, inicio, fim):
    return db.execute(
        """SELECT u.display_name AS nome, u.color AS cor, COALESCE(SUM(t.valor), 0) AS total
           FROM users u LEFT JOIN transactions t
             ON t.user_id = u.id AND t.tipo = 'saida' AND t.data >= ? AND t.data < ?
           GROUP BY u.id ORDER BY u.id""",
        (inicio, fim),
    ).fetchall()


def _grafico_evolucao(db, meses):
    """Configuração lida pelo static/js/app.js para desenhar o gráfico de barras."""
    rotulos, entradas, saidas = [], [], []
    for ano, mes in ultimos_meses(meses):
        inicio, fim = limites_mes(ano, mes)
        rotulos.append(rotulo_mes_curto(ano, mes))
        entradas.append(round(soma(db, "entrada", inicio, fim), 2))
        saidas.append(round(soma(db, "saida", inicio, fim), 2))
    return {
        "tipo": "bar",
        "rotulos": rotulos,
        "series": [
            {"rotulo": "Entrou", "dados": entradas, "cor": "positivo"},
            {"rotulo": "Saiu", "dados": saidas, "cor": "negativo"},
        ],
    }


@bp.route("/")
@login_required
def index():
    db = get_db()
    hoje = date.today()
    inicio, fim = limites_mes(hoje.year, hoje.month)

    entradas = soma(db, "entrada", inicio, fim)
    saidas = soma(db, "saida", inicio, fim)
    guardado = soma(db, caixinhas.DEPOSITO, inicio, fim) - soma(db, caixinhas.RESGATE, inicio, fim)
    saldo = entradas - saidas - guardado

    contas = contas_do_mes(db, competencia_atual())
    resumo_contas = resumo(contas)

    return render_template(
        "inicio/index.html",
        mes=MESES[hoje.month - 1],
        entradas=entradas,
        saidas=saidas,
        guardado=guardado,
        saldo=saldo,
        previsao=saldo - resumo_contas["a_pagar"],
        contas=contas,
        resumo_contas=resumo_contas,
        caixinhas=caixinhas.listar(db),
        total_guardado=caixinhas.total_guardado(db),
        categorias=_gastos_por_categoria(db, inicio, fim, saidas),
        pessoas=_gastos_por_pessoa(db, inicio, fim),
        grafico_evolucao=_grafico_evolucao(db, 6),
        ultimos=ultimos(db, 6),
    )


@bp.route("/mais")
@login_required
def mais():
    return render_template("inicio/mais.html")
