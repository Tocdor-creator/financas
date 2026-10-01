from datetime import date

import pytest

from financas.formatacao import (
    data_br, data_curta, deslocar_mes, formatar_brl, limites_mes, parse_valor, ultimos_meses, vencimento,
)


@pytest.mark.parametrize("texto, esperado", [
    ("1.500", 1500),
    ("1.234,56", 1234.56),
    ("1234,56", 1234.56),
    ("1234.56", 1234.56),
    ("10.5", 10.5),
    ("1234", 1234),
    ("R$ 12.345.678", 12345678),
    ("0,50", 0.5),
    ("0", 0),
])
def test_parse_valor(texto, esperado):
    assert parse_valor(texto) == pytest.approx(esperado)


@pytest.mark.parametrize("texto", ["-50", "abc", "", None])
def test_parse_valor_recusa_invalidos(texto):
    with pytest.raises(ValueError):
        parse_valor(texto)


def test_formatar_brl():
    assert formatar_brl(1234.5) == "R$ 1.234,50"
    assert formatar_brl(1_000_000) == "R$ 1.000.000,00"
    assert formatar_brl(-3) == "-R$ 3,00"
    assert formatar_brl(10, sinal=True) == "+R$ 10,00"


def test_datas():
    assert data_br("2026-09-27") == "27/09/2026"
    assert data_curta("2026-09-05") == "05 set"


def test_limites_e_deslocamento_de_mes():
    assert limites_mes(2026, 12) == ("2026-12-01", "2027-01-01")
    assert deslocar_mes(2026, 1, -1) == (2025, 12)
    assert deslocar_mes(2026, 12, 1) == (2027, 1)
    assert ultimos_meses(3, date(2026, 2, 10)) == [(2025, 12), (2026, 1), (2026, 2)]


def test_vencimento_em_mes_curto_usa_ultimo_dia():
    assert vencimento("2026-02", 31) == date(2026, 2, 28)
    assert vencimento("2026-03", 10) == date(2026, 3, 10)
