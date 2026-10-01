"""Sugestão de categoria aprendida a partir dos lançamentos anteriores."""
import re

# Palavras comuns em extratos que não ajudam a identificar o estabelecimento.
PALAVRAS_IGNORADAS = {
    "COMPRA", "DEBITO", "DÉBITO", "CREDITO", "CRÉDITO", "PARCELA", "PARC",
    "CARTAO", "CARTÃO", "PAGAMENTO", "PGTO", "TRANSFERENCIA", "TRANSFERÊNCIA",
    "PIX", "DE", "EM", "PARA", "A", "O", "DA", "DO", "LTDA", "ME", "EIRELI",
    "S/A", "SA", "NACIONAL", "INTERNACIONAL",
}

ICONES = {
    "Mercado": "carrinho", "Essencial": "raio", "Moradia": "casa", "Transporte": "carro",
    "Saúde": "saude", "Educação": "livro", "Lazer": "ingresso", "Assinaturas": "repetir",
    "Salário": "maleta", "Freelance": "notebook", "Investimento": "caixinha",
}


def icone(categoria):
    return ICONES.get(categoria, "etiqueta")


def normalizar(descricao):
    texto = re.sub(r"\d+", " ", descricao.upper())
    texto = re.sub(r"[^A-ZÀ-Ú\s]", " ", texto)
    return " ".join(p for p in texto.split() if len(p) > 1 and p not in PALAVRAS_IGNORADAS)


def palavra_chave(descricao):
    return " ".join(normalizar(descricao).split()[:3])


def sugerir(db, descricao):
    """Categoria da regra mais específica (palavra-chave mais longa) que combina com a descrição."""
    normalizada = normalizar(descricao)
    if not normalizada:
        return None
    melhor, tamanho = None, 0
    for regra in db.execute("SELECT keyword, categoria FROM category_rules"):
        chave = regra["keyword"]
        if chave and (chave in normalizada or normalizada in chave) and len(chave) > tamanho:
            melhor, tamanho = regra["categoria"], len(chave)
    return melhor


def aprender(db, descricao, categoria):
    chave = palavra_chave(descricao)
    if not categoria or not chave:
        return
    db.execute(
        "INSERT INTO category_rules (keyword, categoria) VALUES (?, ?) "
        "ON CONFLICT (keyword) DO UPDATE SET categoria = excluded.categoria",
        (chave, categoria),
    )
    db.commit()
