import pytest


@pytest.fixture
def caixinha(cliente, db):
    def _caixinha(nome="Viagem", meta=""):
        cliente.post("/caixinhas/nova", data={"nome": nome, "meta": meta, "tipo": "Outro"})
        return db.execute("SELECT id FROM investimentos WHERE nome = ?", (nome,)).fetchone()[0]
    return _caixinha


def movimentar(cliente, caixinha_id, acao, valor, descricao=""):
    return cliente.post(f"/caixinhas/{caixinha_id}/movimentar", data={"acao": acao, "valor": valor, "descricao": descricao})


def saldo(db, caixinha_id):
    from financas.caixinhas import saldo as calcular
    return calcular(db, caixinha_id)


def test_criar_redireciona_para_a_caixinha(cliente, db):
    resposta = cliente.post("/caixinhas/nova", data={"nome": "Carro", "tipo": "Outro"})
    caixinha_id = db.execute("SELECT id FROM investimentos").fetchone()[0]
    assert resposta.headers["Location"].endswith(f"/caixinhas/{caixinha_id}")


def test_meta_invalida_nao_cria(cliente, db):
    cliente.post("/caixinhas/nova", data={"nome": "Reserva", "meta": "abc"})
    assert db.execute("SELECT COUNT(*) FROM investimentos").fetchone()[0] == 0


def test_guardar_resgatar_e_progresso(cliente, db, contexto, caixinha):
    caixinha_id = caixinha(meta="1.000")
    movimentar(cliente, caixinha_id, "guardar", "250")
    movimentar(cliente, caixinha_id, "resgatar", "999")  # maior que o saldo: recusado

    cliente.get(f"/caixinhas/{caixinha_id}")
    assert contexto["caixinha"]["saldo"] == 250
    assert contexto["caixinha"]["progresso"] == 25


def test_guardar_desconta_do_saldo_do_mes(cliente, contexto, caixinha, lancar):
    lancar(tipo="entrada", valor="1000")
    movimentar(cliente, caixinha(), "guardar", "300")
    cliente.get("/")
    assert contexto["saldo"] == 700
    assert contexto["total_guardado"] == 300


def test_apagar_so_com_saldo_zerado(cliente, db, caixinha):
    caixinha_id = caixinha()
    movimentar(cliente, caixinha_id, "guardar", "100")
    cliente.post(f"/caixinhas/{caixinha_id}/apagar")
    assert db.execute("SELECT ativo FROM investimentos WHERE id = ?", (caixinha_id,)).fetchone()[0] == 1

    movimentar(cliente, caixinha_id, "resgatar", "100")
    cliente.post(f"/caixinhas/{caixinha_id}/apagar")
    assert db.execute("SELECT ativo FROM investimentos WHERE id = ?", (caixinha_id,)).fetchone()[0] == 0

    movimentar(cliente, caixinha_id, "guardar", "10")  # caixinha apagada não recebe dinheiro
    assert saldo(db, caixinha_id) == 0


def test_editar_movimento_nao_deixa_saldo_negativo(cliente, db, caixinha, hoje):
    caixinha_id = caixinha()
    movimentar(cliente, caixinha_id, "guardar", "500", "Depósito")
    movimentar(cliente, caixinha_id, "resgatar", "300", "Resgate")
    deposito = db.execute("SELECT id FROM transactions WHERE descricao = 'Depósito'").fetchone()[0]
    resgate = db.execute("SELECT id FROM transactions WHERE descricao = 'Resgate'").fetchone()[0]

    def editar(lancamento_id, valor):
        # tipo e categoria enviados devem ser ignorados em movimentos de caixinha
        cliente.post(f"/lancamentos/{lancamento_id}/editar", data={
            "valor": valor, "data": hoje.isoformat(), "descricao": "x", "tipo": "entrada", "categoria": "Outra",
        })

    editar(deposito, "200")
    editar(resgate, "900")
    assert saldo(db, caixinha_id) == 200

    editar(deposito, "800")
    movimento = db.execute("SELECT * FROM transactions WHERE id = ?", (deposito,)).fetchone()
    assert (movimento["valor"], movimento["tipo"], movimento["categoria"]) == (800, "investimento_deposito", "Investimento")


def test_excluir_deposito_ja_resgatado_e_recusado(cliente, db, caixinha):
    caixinha_id = caixinha()
    movimentar(cliente, caixinha_id, "guardar", "500", "Depósito")
    movimentar(cliente, caixinha_id, "resgatar", "300")
    deposito = db.execute("SELECT id FROM transactions WHERE descricao = 'Depósito'").fetchone()[0]

    cliente.post(f"/lancamentos/{deposito}/excluir")
    assert db.execute("SELECT 1 FROM transactions WHERE id = ?", (deposito,)).fetchone() is not None
