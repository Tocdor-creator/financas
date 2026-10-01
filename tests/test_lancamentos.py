from io import BytesIO

import pytest


def buscar(db, lancamento_id):
    return db.execute("SELECT * FROM transactions WHERE id = ?", (lancamento_id,)).fetchone()


def test_novo_volta_para_o_mes_do_lancamento(cliente):
    resposta = cliente.post("/lancamentos/novo", data={
        "tipo": "saida", "valor": "5", "data": "2026-01-10", "descricao": "Café", "categoria": "",
    })
    assert "mes=2026-01" in resposta.headers["Location"]


def test_novo_com_tipo_invalido_vira_saida(cliente, db, lancar):
    lancamento_id = lancar(tipo="qualquer")
    assert buscar(db, lancamento_id)["tipo"] == "saida"


def test_novo_recusa_valor_invalido(cliente, db):
    cliente.post("/lancamentos/novo", data={"tipo": "saida", "valor": "abc", "data": "2026-01-10", "descricao": "X"})
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_extrato_mostra_so_o_mes_pedido(cliente, contexto, lancar, hoje, mes_seguinte):
    lancar(data=hoje)
    lancar(data=mes_seguinte)
    lancar(data=mes_seguinte)

    cliente.get("/extrato")
    assert sum(len(itens) for _, itens in contexto["dias"]) == 1

    cliente.get(f"/extrato?mes={mes_seguinte:%Y-%m}")
    assert sum(len(itens) for _, itens in contexto["dias"]) == 2


def test_extrato_com_mes_invalido_usa_o_mes_atual(cliente, contexto, hoje):
    cliente.get("/extrato?mes=lixo")
    assert contexto["mes"] == f"{hoje:%Y-%m}"


def test_editar(cliente, db, lancar):
    lancamento_id = lancar(valor="50", descricao="Padaria")
    resposta = cliente.get(f"/lancamentos/{lancamento_id}/editar")
    assert 'value="50,00"' in resposta.get_data(as_text=True)

    resposta = cliente.post(f"/lancamentos/{lancamento_id}/editar", data={
        "voltar": "/extrato?tipo=saida", "tipo": "entrada", "valor": "1.234,56",
        "data": "2026-08-15", "descricao": "Padaria Central", "categoria": "Lazer",
    })
    salvo = buscar(db, lancamento_id)
    assert (salvo["tipo"], salvo["valor"], salvo["data"], salvo["descricao"], salvo["categoria"]) == (
        "entrada", 1234.56, "2026-08-15", "Padaria Central", "Lazer")
    assert resposta.headers["Location"].endswith("/extrato?tipo=saida")


@pytest.mark.parametrize("campos", [
    {"valor": "abc"},
    {"valor": "0"},
    {"data": "ontem"},
    {"descricao": "   "},
])
def test_editar_recusa_dados_invalidos(cliente, db, lancar, campos):
    lancamento_id = lancar(valor="50", descricao="Original")
    dados = {"tipo": "saida", "valor": "10", "data": "2026-08-15", "descricao": "Novo"} | campos
    cliente.post(f"/lancamentos/{lancamento_id}/editar", data=dados)
    assert buscar(db, lancamento_id)["descricao"] == "Original"


@pytest.mark.parametrize("destino", ["https://exemplo.com", "//exemplo.com"])
def test_voltar_so_aceita_caminho_interno(cliente, lancar, destino):
    lancamento_id = lancar()
    resposta = cliente.post(f"/lancamentos/{lancamento_id}/editar", data={
        "voltar": destino, "tipo": "saida", "valor": "10", "data": "2026-08-15", "descricao": "X",
    })
    assert "exemplo.com" not in resposta.headers["Location"]


def test_comprovante_adicionar_manter_e_remover(app, cliente, db, lancar):
    lancamento_id = lancar()
    dados = {"tipo": "saida", "valor": "10", "data": "2026-08-15", "descricao": "Com nota"}

    cliente.post(f"/lancamentos/{lancamento_id}/editar", content_type="multipart/form-data",
                 data=dados | {"comprovante": (BytesIO(b"%PDF-1.4"), "nota.pdf")})
    arquivo = buscar(db, lancamento_id)["comprovante"]
    assert arquivo.endswith("nota.pdf")
    assert cliente.get(f"/arquivos/comprovantes/{arquivo}").status_code == 200

    cliente.post(f"/lancamentos/{lancamento_id}/editar", data=dados)
    assert buscar(db, lancamento_id)["comprovante"] == arquivo

    cliente.post(f"/lancamentos/{lancamento_id}/editar", data=dados | {"remover_comprovante": "on"})
    assert buscar(db, lancamento_id)["comprovante"] is None


def test_excluir(cliente, db, lancar):
    lancamento_id = lancar()
    resposta = cliente.post(f"/lancamentos/{lancamento_id}/excluir", data={"voltar": "/extrato"})
    assert buscar(db, lancamento_id) is None
    assert resposta.headers["Location"].endswith("/extrato")


def test_editar_lancamento_inexistente(cliente):
    assert cliente.get("/lancamentos/999/editar").status_code == 302


def test_categoria_aprendida_e_sugerida(app, db, lancar):
    from financas import categorias

    lancar(descricao="COMPRA SUPERMERCADO BOM PRECO 123", categoria="Mercado")
    assert categorias.sugerir(db, "SUPERMERCADO BOM PRECO LTDA") == "Mercado"
