import pytest


@pytest.fixture
def conta(cliente, db):
    """Cadastra uma conta fixa e devolve o id do pagamento pendente do mês atual."""
    def _conta(descricao="Internet", valor="100", dia="15"):
        cliente.post("/contas/nova", data={"descricao": descricao, "valor": valor, "dia_vencimento": dia})
        cliente.get("/contas/")
        return db.execute(
            "SELECT p.id FROM pagamentos_fixos p JOIN contas_fixas c ON c.id = p.conta_fixa_id WHERE c.descricao = ?",
            (descricao,),
        ).fetchone()[0]
    return _conta


def pagamento(db, pagamento_id):
    return db.execute("SELECT * FROM pagamentos_fixos WHERE id = ?", (pagamento_id,)).fetchone()


def pagar(cliente, pagamento_id, hoje, valor="100,00"):
    cliente.post(f"/contas/pagamentos/{pagamento_id}/pagar", data={
        "valor": valor, "data_pagamento": hoje.isoformat(), "categoria": "Moradia",
    })


@pytest.mark.parametrize("dia", ["abc", ""])
def test_dia_de_vencimento_invalido(cliente, db, dia):
    resposta = cliente.post("/contas/nova", data={"descricao": "Luz", "valor": "150", "dia_vencimento": dia})
    assert resposta.status_code == 302
    assert db.execute("SELECT COUNT(*) FROM contas_fixas").fetchone()[0] == 0


def test_pagar_cria_saida(cliente, db, conta, hoje):
    pagamento_id = conta()
    assert cliente.get(f"/contas/pagamentos/{pagamento_id}/pagar").status_code == 200
    pagar(cliente, pagamento_id, hoje)
    pago = pagamento(db, pagamento_id)
    saida = db.execute("SELECT * FROM transactions WHERE id = ?", (pago["transaction_id"],)).fetchone()
    assert pago["status"] == "pago"
    assert (saida["tipo"], saida["valor"], saida["origem"]) == ("saida", 100, "conta_fixa")


def test_desfazer_pagamento(cliente, db, conta, hoje):
    pagamento_id = conta()
    pagar(cliente, pagamento_id, hoje)
    cliente.post(f"/contas/pagamentos/{pagamento_id}/desfazer")
    assert pagamento(db, pagamento_id)["status"] == "pendente"
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_excluir_a_saida_reabre_a_conta(cliente, db, conta, hoje):
    pagamento_id = conta()
    pagar(cliente, pagamento_id, hoje)
    cliente.post(f"/lancamentos/{pagamento(db, pagamento_id)['transaction_id']}/excluir")
    reaberto = pagamento(db, pagamento_id)
    assert reaberto["status"] == "pendente" and reaberto["transaction_id"] is None


def test_editar_pagamento_atualiza_a_conta_e_continua_saida(cliente, db, conta, hoje):
    pagamento_id = conta()
    pagar(cliente, pagamento_id, hoje)
    lancamento_id = pagamento(db, pagamento_id)["transaction_id"]

    cliente.post(f"/lancamentos/{lancamento_id}/editar", data={
        "tipo": "entrada", "valor": "97,40", "data": hoje.isoformat(), "descricao": "Internet",
    })
    assert pagamento(db, pagamento_id)["valor"] == 97.40
    assert db.execute("SELECT tipo FROM transactions WHERE id = ?", (lancamento_id,)).fetchone()[0] == "saida"


def test_remover_conta_apaga_pendencias(cliente, db, conta, contexto):
    pagamento_id = conta()
    conta_id = pagamento(db, pagamento_id)["conta_fixa_id"]
    cliente.post(f"/contas/{conta_id}/remover")
    assert pagamento(db, pagamento_id) is None

    cliente.get("/")
    assert contexto["resumo_contas"]["a_pagar"] == 0


def test_conta_atrasada_de_mes_anterior_aparece(cliente, db, conta, contexto):
    pagamento_id = conta()
    conta_id = pagamento(db, pagamento_id)["conta_fixa_id"]
    db.execute(
        "INSERT INTO pagamentos_fixos (conta_fixa_id, competencia, valor, status) VALUES (?, '2025-12', 100, 'pendente')",
        (conta_id,),
    )
    db.commit()

    cliente.get("/contas/")
    assert contexto["resumo"]["a_pagar"] == 200
    atrasada = next(c for c in contexto["contas"] if c["competencia"] == "2025-12")
    assert atrasada["situacao"] == "vencida"
