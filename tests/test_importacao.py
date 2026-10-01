from datetime import date
from io import BytesIO

import pytest

from financas.importacao import extrair_lancamentos, interpretar_data

JANEIRO = date(2027, 1, 5)


@pytest.mark.parametrize("texto, esperado", [
    ("20/12", date(2026, 12, 20)),      # fatura de dezembro lida em janeiro
    ("03/01", date(2027, 1, 3)),
    ("15/03/2026", date(2026, 3, 15)),
    ("15/03/26", date(2026, 3, 15)),
])
def test_interpretar_data(texto, esperado):
    assert interpretar_data(texto, hoje=JANEIRO) == esperado


def test_interpretar_data_invalida():
    with pytest.raises(ValueError):
        interpretar_data("29/02", hoje=JANEIRO)  # nem 2027 nem 2026 são bissextos


def test_extrair_lancamentos():
    texto = "\n".join([
        "03/01/2027 SUPERMERCADO BOM PRECO 1.234,56",
        "04/01/2027 SALARIO EMPRESA + 5.000,00",
        "linha qualquer sem valor",
        "05/01/2027 12 34,00",
    ])
    lancamentos = extrair_lancamentos(texto, lambda descricao: "Mercado" if "SUPER" in descricao else None)

    assert lancamentos == [
        {"data": "2027-01-03", "descricao": "SUPERMERCADO BOM PRECO", "valor": 1234.56, "tipo": "saida", "categoria": "Mercado"},
        {"data": "2027-01-04", "descricao": "SALARIO EMPRESA", "valor": 5000.0, "tipo": "entrada", "categoria": ""},
    ]


def test_importacao_completa(cliente, db, monkeypatch):
    lidos = [{"data": "2026-09-01", "descricao": "Padaria", "valor": 12.5, "tipo": "saida", "categoria": ""}]
    monkeypatch.setattr("financas.importacao.ler_pdf", lambda caminho, sugerir: lidos)

    resposta = cliente.post("/importar/", data={"pdf": (BytesIO(b"%PDF"), "extrato.pdf")}, content_type="multipart/form-data")
    assert resposta.headers["Location"].endswith("/importar/revisar")
    assert cliente.get("/importar/revisar").status_code == 200

    cliente.post("/importar/revisar", data={
        "incluir_0": "on", "tipo_0": "saida", "data_0": "2026-09-01",
        "descricao_0": "Padaria", "valor_0": "12,50", "categoria_0": "Mercado",
    })
    salvo = db.execute("SELECT * FROM transactions").fetchone()
    assert (salvo["descricao"], salvo["valor"], salvo["origem"]) == ("Padaria", 12.5, "pdf")
