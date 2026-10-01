"""Importação de extratos e faturas em PDF, com revisão antes de salvar."""
import os
import re
import tempfile
from datetime import date, datetime, timedelta

import pdfplumber
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from . import categorias
from .auth import login_required
from .config import CATEGORIAS
from .db import get_db
from .formatacao import parse_valor

bp = Blueprint("importacao", __name__, url_prefix="/importar")

# data (dd/mm ou dd/mm/aa[aa]) + descrição + valor no fim da linha, com sinal opcional
LINHA_EXTRATO = re.compile(
    r"(?P<data>\d{2}[/.]\d{2}(?:[/.]\d{2,4})?)\s+(?P<desc>.+?)\s+"
    r"(?P<sinal>[-+])?\s?R?\$?\s?(?P<valor>(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2})\s*$"
)
# Datas sem ano que caem além disso no futuro são do ano anterior (ex.: fatura de dezembro lida em janeiro).
MARGEM_FUTURO = timedelta(days=60)


def interpretar_data(texto, hoje=None):
    """Converte 'dd/mm', 'dd/mm/aa' ou 'dd/mm/aaaa' em date. Lança ValueError se inválida."""
    hoje = hoje or date.today()
    partes = re.split(r"[/.]", texto)
    if len(partes) == 3:
        dia, mes, ano = partes
        return date(int(ano) + (2000 if len(ano) == 2 else 0), int(mes), int(dia))

    dia, mes = int(partes[0]), int(partes[1])
    try:
        candidata = date(hoje.year, mes, dia)
    except ValueError:  # 29/02 em ano não bissexto
        candidata = None
    if candidata is None or candidata > hoje + MARGEM_FUTURO:
        candidata = date(hoje.year - 1, mes, dia)
    return candidata


def extrair_lancamentos(texto, sugerir_categoria):
    """Lê as linhas reconhecíveis do texto de um extrato. Linhas que não batem com o padrão são ignoradas."""
    encontrados = []
    for linha in texto.splitlines():
        m = LINHA_EXTRATO.search(linha.strip())
        if not m:
            continue
        descricao = m.group("desc").strip()
        if len(descricao) < 3 or re.fullmatch(r"[\d\s./-]+", descricao):
            continue
        try:
            data = interpretar_data(m.group("data"))
        except ValueError:
            continue
        encontrados.append({
            "data": data.isoformat(),
            "descricao": descricao,
            "valor": parse_valor(m.group("valor")),
            "tipo": "entrada" if m.group("sinal") == "+" else "saida",
            "categoria": sugerir_categoria(descricao) or "",
        })
    return encontrados


def ler_pdf(caminho, sugerir_categoria):
    with pdfplumber.open(caminho) as pdf:
        texto = "\n".join(pagina.extract_text() or "" for pagina in pdf.pages)
    return extrair_lancamentos(texto, sugerir_categoria)


@bp.route("/", methods=["GET", "POST"])
@login_required
def enviar():
    if request.method == "GET":
        return render_template("importacao/enviar.html")

    arquivo = request.files.get("pdf")
    if not arquivo or not arquivo.filename.lower().endswith(".pdf"):
        flash("Envie um arquivo PDF.", "error")
        return redirect(url_for("importacao.enviar"))

    db = get_db()
    descritor, caminho = tempfile.mkstemp(suffix=".pdf")
    os.close(descritor)
    try:
        arquivo.save(caminho)
        lancamentos = ler_pdf(caminho, lambda descricao: categorias.sugerir(db, descricao))
    except Exception:
        flash("Não foi possível ler esse PDF. Ele pode estar protegido ou ser uma imagem digitalizada.", "error")
        return redirect(url_for("importacao.enviar"))
    finally:
        os.remove(caminho)

    if not lancamentos:
        flash("Nenhum lançamento reconhecido nesse PDF. Você pode lançar manualmente.", "error")
        return redirect(url_for("importacao.enviar"))
    session["importacao"] = lancamentos
    return redirect(url_for("importacao.revisar"))


@bp.route("/revisar", methods=["GET", "POST"])
@login_required
def revisar():
    lancamentos = session.get("importacao")
    if not lancamentos:
        flash("Não há importação pendente. Envie o PDF novamente.", "error")
        return redirect(url_for("importacao.enviar"))
    if request.method == "GET":
        return render_template("importacao/revisar.html", lancamentos=lancamentos, categorias=CATEGORIAS)

    db = get_db()
    salvos = ignorados = 0
    for i in range(len(lancamentos)):
        if request.form.get(f"incluir_{i}") != "on":
            continue
        tipo = request.form.get(f"tipo_{i}")
        descricao = request.form.get(f"descricao_{i}", "").strip()
        categoria = request.form.get(f"categoria_{i}", "").strip() or None
        try:
            valor = parse_valor(request.form.get(f"valor_{i}"))
            data = date.fromisoformat(request.form.get(f"data_{i}", "")).isoformat()
        except ValueError:
            ignorados += 1
            continue
        if tipo not in ("entrada", "saida") or not descricao:
            ignorados += 1
            continue
        db.execute(
            """INSERT INTO transactions (user_id, tipo, valor, data, descricao, categoria, origem, criado_em)
               VALUES (?, ?, ?, ?, ?, ?, 'pdf', ?)""",
            (g.user["id"], tipo, valor, data, descricao, categoria, datetime.now().isoformat()),
        )
        if tipo == "saida":
            categorias.aprender(db, descricao, categoria)
        salvos += 1
    db.commit()
    session.pop("importacao", None)

    mensagem = f"{salvos} lançamento(s) importado(s)."
    if ignorados:
        mensagem += f" {ignorados} linha(s) ignorada(s) por data ou valor inválido."
    flash(mensagem, "success" if salvos else "error")
    return redirect(url_for("inicio.index" if salvos else "importacao.enviar"))
