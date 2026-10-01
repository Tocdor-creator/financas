import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CATEGORIAS = [
    "Mercado", "Essencial", "Moradia", "Transporte", "Saúde", "Educação",
    "Lazer", "Assinaturas", "Salário", "Freelance", "Investimento", "Outros",
]

TIPOS_CAIXINHA = ["CDI Fixo", "Selic", "Poupança", "Variável", "Fundo de Investimento Variável", "Outro"]

TEMAS = {
    "roxo": {"nome": "Roxo", "cor": "#820ad1"},
    "rosa": {"nome": "Rosa", "cor": "#d63384"},
    "azul": {"nome": "Azul", "cor": "#0b6bcb"},
    "verde": {"nome": "Verde", "cor": "#0a8754"},
    "laranja": {"nome": "Laranja", "cor": "#d9480f"},
}
TEMA_PADRAO = "roxo"

MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_MINUTOS = 15


def carregar_chave_secreta(caminho):
    """Lê a chave de sessão do disco, criando-a na primeira execução, para o login sobreviver a reinícios."""
    if not os.path.exists(caminho):
        with open(caminho, "wb") as f:
            f.write(os.urandom(32))
    with open(caminho, "rb") as f:
        return f.read()


def configuracao_padrao():
    return {
        "DATABASE": os.path.join(BASE_DIR, "financas.db"),
        "PASTA_COMPROVANTES": os.path.join(BASE_DIR, "comprovantes"),
        "PASTA_FOTOS": os.path.join(BASE_DIR, "sonhos"),
        "ARQUIVO_CHAVE": os.path.join(BASE_DIR, "secret.key"),
    }
