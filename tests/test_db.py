import sqlite3

from financas.db import init_db


def test_migracao_de_banco_antigo(tmp_path):
    """Banco de uma versão anterior: mural de sonhos e pagamentos inconsistentes são corrigidos."""
    caminho = tmp_path / "antigo.db"
    with sqlite3.connect(caminho) as db:
        db.executescript("""
            CREATE TABLE investimentos (id INTEGER PRIMARY KEY, nome TEXT NOT NULL, tipo TEXT,
                                        ativo INTEGER DEFAULT 1, criado_em TEXT NOT NULL);
            CREATE TABLE sonhos (id INTEGER PRIMARY KEY, filename TEXT, legenda TEXT, user_id INTEGER, criado_em TEXT);
            INSERT INTO sonhos (filename, legenda, user_id, criado_em) VALUES ('casa.png', 'Casa própria', 1, 'x');
            CREATE TABLE contas_fixas (id INTEGER PRIMARY KEY, descricao TEXT NOT NULL, valor REAL NOT NULL,
                                       categoria TEXT, dia_vencimento INTEGER NOT NULL, ativo INTEGER DEFAULT 1,
                                       criado_em TEXT NOT NULL);
            INSERT INTO contas_fixas VALUES (1, 'Antiga', 50, NULL, 5, 0, 'x');
            INSERT INTO contas_fixas VALUES (2, 'Luz', 90, NULL, 5, 1, 'x');
            CREATE TABLE pagamentos_fixos (id INTEGER PRIMARY KEY, conta_fixa_id INTEGER NOT NULL,
                                           competencia TEXT NOT NULL, valor REAL NOT NULL, status TEXT DEFAULT 'pendente',
                                           data_pagamento TEXT, comprovante TEXT, transaction_id INTEGER,
                                           UNIQUE (conta_fixa_id, competencia));
            INSERT INTO pagamentos_fixos (conta_fixa_id, competencia, valor) VALUES (1, '2026-01', 50);
            INSERT INTO pagamentos_fixos (conta_fixa_id, competencia, valor, status, transaction_id)
                VALUES (2, '2026-01', 90, 'pago', 999);
        """)

    init_db(caminho)
    init_db(caminho)  # rodar de novo não pode duplicar nada

    with sqlite3.connect(caminho) as db:
        assert db.execute("SELECT nome, foto FROM investimentos").fetchall() == [("Casa própria", "casa.png")]
        assert db.execute("SELECT COUNT(*) FROM sonhos").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM pagamentos_fixos WHERE conta_fixa_id = 1").fetchone()[0] == 0
        assert db.execute("SELECT status FROM pagamentos_fixos WHERE conta_fixa_id = 2").fetchone()[0] == "pendente"
