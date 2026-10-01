import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    color TEXT DEFAULT '#820ad1',
    tema TEXT DEFAULT 'roxo'
);

-- tipo: entrada | saida | investimento_deposito | investimento_resgate
-- origem: manual | pdf | conta_fixa
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id),
    tipo TEXT NOT NULL,
    valor REAL NOT NULL,
    data TEXT NOT NULL,
    descricao TEXT NOT NULL,
    categoria TEXT,
    origem TEXT DEFAULT 'manual',
    comprovante TEXT,
    investimento_id INTEGER,
    criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS category_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT UNIQUE NOT NULL,
    categoria TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contas_fixas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL,
    categoria TEXT,
    responsavel TEXT,
    dia_vencimento INTEGER NOT NULL,
    ativo INTEGER DEFAULT 1,
    criado_em TEXT NOT NULL
);

-- uma linha por conta fixa e mês (competencia = YYYY-MM); status: pendente | pago
CREATE TABLE IF NOT EXISTS pagamentos_fixos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conta_fixa_id INTEGER NOT NULL REFERENCES contas_fixas (id),
    competencia TEXT NOT NULL,
    valor REAL NOT NULL,
    status TEXT DEFAULT 'pendente',
    data_pagamento TEXT,
    comprovante TEXT,
    transaction_id INTEGER,
    UNIQUE (conta_fixa_id, competencia)
);

-- caixinhas
CREATE TABLE IF NOT EXISTS investimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    tipo TEXT,
    meta REAL,
    foto TEXT,
    ativo INTEGER DEFAULT 1,
    criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS previsoes_mensais (
    competencia TEXT PRIMARY KEY,
    planejado_gastos REAL DEFAULT 0,
    planejado_ganhos REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS login_attempts (
    username TEXT PRIMARY KEY,
    tentativas INTEGER DEFAULT 0,
    bloqueado_ate TEXT
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(caminho):
    db = sqlite3.connect(caminho)
    try:
        db.executescript(SCHEMA)
        _migrar(db)
        db.commit()
    finally:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    init_db(app.config["DATABASE"])


def _colunas(db, tabela):
    return {linha[1] for linha in db.execute(f"PRAGMA table_info({tabela})")}


def _adicionar_coluna(db, tabela, coluna, declaracao):
    if coluna not in _colunas(db, tabela):
        db.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {declaracao}")


def _migrar(db):
    """Atualiza bancos criados por versões anteriores. Tudo aqui precisa ser idempotente."""
    _adicionar_coluna(db, "transactions", "comprovante", "TEXT")
    _adicionar_coluna(db, "transactions", "investimento_id", "INTEGER")
    _adicionar_coluna(db, "contas_fixas", "responsavel", "TEXT")
    _adicionar_coluna(db, "users", "tema", "TEXT DEFAULT 'roxo'")
    _adicionar_coluna(db, "investimentos", "meta", "REAL")
    _adicionar_coluna(db, "investimentos", "foto", "TEXT")

    db.execute("UPDATE transactions SET tipo = 'investimento_deposito' WHERE tipo = 'futuro_deposito'")
    db.execute("UPDATE transactions SET tipo = 'investimento_resgate' WHERE tipo = 'futuro_resgate'")

    # O antigo mural de sonhos virou caixinhas: cada foto vira uma caixinha.
    if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sonhos'").fetchone():
        for id_, arquivo, legenda, criado_em in db.execute("SELECT id, filename, legenda, criado_em FROM sonhos").fetchall():
            db.execute(
                "INSERT INTO investimentos (nome, tipo, ativo, criado_em, foto) VALUES (?, 'Outro', 1, ?, ?)",
                (legenda or "Meu sonho", criado_em, arquivo),
            )
            db.execute("DELETE FROM sonhos WHERE id = ?", (id_,))

    # Corrige dados gravados antes de desativar conta / excluir lançamento manterem os pagamentos coerentes.
    db.execute(
        "DELETE FROM pagamentos_fixos WHERE status = 'pendente' "
        "AND conta_fixa_id IN (SELECT id FROM contas_fixas WHERE ativo = 0)"
    )
    db.execute(
        "UPDATE pagamentos_fixos SET status = 'pendente', data_pagamento = NULL, transaction_id = NULL, comprovante = NULL "
        "WHERE status = 'pago' AND transaction_id IS NOT NULL "
        "AND transaction_id NOT IN (SELECT id FROM transactions)"
    )
