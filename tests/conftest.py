import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from flask import template_rendered
from werkzeug.security import generate_password_hash

from financas import create_app
from financas.formatacao import deslocar_mes

SENHA = "senha123"
SENHA_HASH = generate_password_hash(SENHA)  # gerado uma vez: o hash é lento de propósito


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "teste",
        "DATABASE": str(tmp_path / "teste.db"),
        "PASTA_COMPROVANTES": str(tmp_path / "comprovantes"),
        "PASTA_FOTOS": str(tmp_path / "fotos"),
    })
    with banco(app) as db:
        for username, nome in (("ana", "Ana"), ("beto", "Beto")):
            db.execute(
                "INSERT INTO users (username, display_name, password_hash) VALUES (?, ?, ?)",
                (username, nome, SENHA_HASH),
            )
    return app


@contextmanager
def banco(app):
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


@pytest.fixture
def db(app):
    """Conexão direta com o banco de teste, para preparar e conferir dados."""
    with banco(app) as conexao:
        yield conexao


@pytest.fixture
def anonimo(app):
    return app.test_client()


@pytest.fixture
def cliente(app):
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["user_id"] = 1
    return cliente


@pytest.fixture
def contexto(app):
    """Contexto do último template renderizado."""
    capturado = {}

    def registrar(sender, template, context, **extra):
        capturado.clear()
        capturado.update(context)

    template_rendered.connect(registrar, app)
    yield capturado
    template_rendered.disconnect(registrar, app)


@pytest.fixture
def hoje():
    return date.today()


@pytest.fixture
def mes_seguinte(hoje):
    ano, mes = deslocar_mes(hoje.year, hoje.month, 1)
    return date(ano, mes, 5)


@pytest.fixture
def ontem(hoje):
    return hoje - timedelta(days=1)


@pytest.fixture
def lancar(cliente, db):
    """Cria um lançamento pela rota de cadastro e devolve o id."""
    def _lancar(tipo="saida", valor="100", data=None, descricao="Teste", categoria="Mercado"):
        resposta = cliente.post("/lancamentos/novo", data={
            "tipo": tipo, "valor": valor, "data": (data or date.today()).isoformat(),
            "descricao": descricao, "categoria": categoria,
        })
        assert resposta.status_code == 302
        return db.execute("SELECT MAX(id) FROM transactions").fetchone()[0]
    return _lancar
