"""Conversão e formatação de valores e datas no padrão brasileiro."""
import calendar
import re
from datetime import date, timedelta

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def parse_valor(texto):
    """Converte '1.234,56', '1234,56', '1.500', '1234.56' ou '1234' em float.

    Só com ponto, grupos de três dígitos são milhar ('1.500' = 1500); senão o ponto é decimal ('10.5').
    Lança ValueError para texto vazio, inválido ou negativo.
    """
    s = str(texto or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        raise ValueError("valor vazio")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", s):
        s = s.replace(".", "")
    valor = float(s)
    if valor < 0:
        raise ValueError("valor negativo")
    return valor


def formatar_brl(valor, sinal=False):
    valor = valor or 0
    numero = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    prefixo = "-" if valor < 0 else ("+" if sinal and valor > 0 else "")
    return f"{prefixo}R$ {numero}"


def valor_para_input(valor):
    return f"{valor or 0:.2f}".replace(".", ",")


def _para_data(valor):
    return date.fromisoformat(valor[:10]) if isinstance(valor, str) else valor


def data_br(valor):
    return _para_data(valor).strftime("%d/%m/%Y") if valor else ""


def data_curta(valor):
    d = _para_data(valor)
    return f"{d.day:02d} {MESES_CURTOS[d.month - 1]}" if d else ""


def dia_relativo(valor):
    d = _para_data(valor)
    hoje = date.today()
    if d == hoje:
        return "Hoje"
    if d == hoje - timedelta(days=1):
        return "Ontem"
    texto = f"{d.day} de {MESES[d.month - 1]}"
    return texto if d.year == hoje.year else f"{texto} de {d.year}"


def nome_mes(ano, mes):
    return f"{MESES[mes - 1].capitalize()} {ano}"


def rotulo_mes_curto(ano, mes):
    return f"{MESES_CURTOS[mes - 1]}/{str(ano)[2:]}"


def limites_mes(ano, mes):
    """Primeiro dia do mês e do mês seguinte, para filtrar com `data >= inicio AND data < fim`."""
    inicio = date(ano, mes, 1)
    fim = date(ano + (mes == 12), mes % 12 + 1, 1)
    return inicio.isoformat(), fim.isoformat()


def deslocar_mes(ano, mes, delta):
    indice = ano * 12 + (mes - 1) + delta
    return indice // 12, indice % 12 + 1


def ultimos_meses(quantidade, hoje=None):
    """(ano, mês) dos últimos `quantidade` meses, do mais antigo ao atual."""
    hoje = hoje or date.today()
    return [deslocar_mes(hoje.year, hoje.month, -i) for i in range(quantidade - 1, -1, -1)]


def vencimento(competencia, dia):
    """Data de vencimento no mês `competencia` (YYYY-MM); dia 31 em mês curto vira o último dia."""
    ano, mes = map(int, competencia.split("-"))
    return date(ano, mes, min(int(dia), calendar.monthrange(ano, mes)[1]))


def registrar_filtros(app):
    app.add_template_filter(formatar_brl, "brl")
    app.add_template_filter(valor_para_input, "valor_input")
    app.add_template_filter(data_br, "data_br")
    app.add_template_filter(data_curta, "data_curta")
    app.add_template_filter(dia_relativo, "dia_relativo")
