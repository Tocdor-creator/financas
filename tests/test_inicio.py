import pytest


def test_inicio_considera_so_o_mes_atual(cliente, contexto, lancar, hoje, mes_seguinte):
    lancar(tipo="entrada", valor="1000", data=hoje)
    lancar(tipo="saida", valor="300", data=hoje, categoria="Mercado")
    lancar(tipo="saida", valor="999", data=mes_seguinte)

    cliente.get("/")
    assert (contexto["entradas"], contexto["saidas"], contexto["saldo"]) == (1000, 300, 700)
    assert [c["total"] for c in contexto["categorias"]] == [300]
    assert contexto["pessoas"][0]["total"] == 300


def test_previsao_desconta_contas_pendentes(cliente, contexto, lancar):
    lancar(tipo="entrada", valor="1000")
    cliente.post("/contas/nova", data={"descricao": "Aluguel", "valor": "800", "dia_vencimento": "10"})

    cliente.get("/")
    assert contexto["previsao"] == 200
    assert "R$ 1.000,00" in cliente.get("/").get_data(as_text=True)


@pytest.mark.parametrize("url", [
    "/", "/mais", "/extrato", "/lancamentos/novo", "/contas/", "/caixinhas/",
    "/previsao/", "/importar/", "/perfil/",
])
def test_paginas_abrem(cliente, url, monkeypatch):
    monkeypatch.setattr("financas.taxas._buscar", lambda serie: None)  # sem acesso à internet nos testes
    assert cliente.get(url).status_code == 200


def test_planejamento_da_previsao(cliente, db, hoje):
    competencia = f"{hoje:%Y-%m}"
    cliente.post("/previsao/", data={"competencia": competencia, "planejado_gastos": "2.000", "planejado_ganhos": "5.000,50"})
    plano = db.execute("SELECT * FROM previsoes_mensais WHERE competencia = ?", (competencia,)).fetchone()
    assert (plano["planejado_gastos"], plano["planejado_ganhos"]) == (2000, 5000.5)
