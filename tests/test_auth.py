import sqlite3

from financas import create_app
from financas.config import MAX_TENTATIVAS_LOGIN


def entrar(cliente, senha="senha123", usuario="ana"):
    return cliente.post("/login", data={"username": usuario, "password": senha})


def test_sem_login_redireciona(anonimo):
    resposta = anonimo.get("/")
    assert resposta.status_code == 302 and resposta.headers["Location"].endswith("/login")


def test_login_e_logout(anonimo):
    assert entrar(anonimo).headers["Location"].endswith("/")
    assert anonimo.get("/").status_code == 200
    anonimo.get("/logout")
    assert anonimo.get("/").status_code == 302


def test_bloqueia_depois_de_tentativas_erradas(anonimo):
    for _ in range(MAX_TENTATIVAS_LOGIN):
        entrar(anonimo, senha="errada")
    resposta = entrar(anonimo)  # senha certa, mas bloqueado
    assert resposta.status_code == 200
    assert "Muitas tentativas" in resposta.get_data(as_text=True)


def test_banco_vazio_pede_configuracao(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "teste", "DATABASE": str(tmp_path / "vazio.db")})
    cliente = app.test_client()
    assert cliente.get("/").headers["Location"].endswith("/configurar")

    cliente.post("/configurar", data={
        "display1": "Ana", "username1": "Ana", "password1": "a",
        "display2": "Beto", "username2": "beto", "password2": "b",
    })
    with sqlite3.connect(tmp_path / "vazio.db") as db:
        assert [r[0] for r in db.execute("SELECT username FROM users ORDER BY id")] == ["ana", "beto"]


def test_trocar_senha(cliente, anonimo):
    cliente.post("/perfil/senha", data={"senha_atual": "senha123", "senha_nova": "nova1234", "senha_confirmar": "nova1234"})
    assert entrar(anonimo, senha="nova1234").headers["Location"].endswith("/")
