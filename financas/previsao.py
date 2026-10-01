from flask import Blueprint, flash, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .formatacao import limites_mes, nome_mes, parse_valor, rotulo_mes_curto, ultimos_meses
from .lancamentos import soma

bp = Blueprint("previsao", __name__, url_prefix="/previsao")

MESES_EXIBIDOS = 6


def _meses(db):
    meses = []
    for ano, mes in ultimos_meses(MESES_EXIBIDOS):
        competencia = f"{ano:04d}-{mes:02d}"
        inicio, fim = limites_mes(ano, mes)
        plano = db.execute("SELECT * FROM previsoes_mensais WHERE competencia = ?", (competencia,)).fetchone()
        meses.append({
            "competencia": competencia,
            "nome": nome_mes(ano, mes),
            "rotulo": rotulo_mes_curto(ano, mes),
            "planejado_gastos": plano["planejado_gastos"] if plano else 0,
            "planejado_ganhos": plano["planejado_ganhos"] if plano else 0,
            "gastos": round(soma(db, "saida", inicio, fim), 2),
            "ganhos": round(soma(db, "entrada", inicio, fim), 2),
        })
    return meses


def _grafico(meses):
    def serie(rotulo, campo, cor, tracejado):
        return {"rotulo": rotulo, "dados": [m[campo] for m in meses], "cor": cor, "tracejado": tracejado}

    return {
        "tipo": "line",
        "rotulos": [m["rotulo"] for m in meses],
        "series": [
            serie("Gastos planejados", "planejado_gastos", "negativo", True),
            serie("Gastos reais", "gastos", "negativo", False),
            serie("Ganhos planejados", "planejado_ganhos", "positivo", True),
            serie("Ganhos reais", "ganhos", "positivo", False),
        ],
    }


@bp.route("/")
@login_required
def index():
    meses = _meses(get_db())
    return render_template("previsao/index.html", meses=meses, grafico=_grafico(meses))


@bp.route("/", methods=["POST"])
@login_required
def salvar():
    db = get_db()
    competencias = request.form.getlist("competencia")
    gastos = request.form.getlist("planejado_gastos")
    ganhos = request.form.getlist("planejado_ganhos")
    ignorados = 0
    for competencia, gasto, ganho in zip(competencias, gastos, ganhos):
        try:
            valores = (parse_valor(gasto or "0"), parse_valor(ganho or "0"))
        except ValueError:
            ignorados += 1
            continue
        db.execute(
            """INSERT INTO previsoes_mensais (competencia, planejado_gastos, planejado_ganhos) VALUES (?, ?, ?)
               ON CONFLICT (competencia) DO UPDATE SET
                 planejado_gastos = excluded.planejado_gastos, planejado_ganhos = excluded.planejado_ganhos""",
            (competencia, *valores),
        )
    db.commit()
    if ignorados:
        flash(f"Planejamento salvo, exceto {ignorados} mês(es) com valor inválido.", "error")
    else:
        flash("Planejamento salvo.", "success")
    return redirect(url_for("previsao.index"))
