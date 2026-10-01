from flask import Flask

from . import arquivos, auth, caixinhas, categorias, contas, db, importacao, inicio, lancamentos, perfil, previsao
from .config import carregar_chave_secreta, configuracao_padrao
from .formatacao import registrar_filtros


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(configuracao_padrao())
    app.config.update(config or {})
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = carregar_chave_secreta(app.config["ARQUIVO_CHAVE"])

    db.init_app(app)
    registrar_filtros(app)
    app.add_template_filter(categorias.icone, "icone_categoria")

    for modulo in (auth, inicio, lancamentos, contas, caixinhas, previsao, importacao, perfil, arquivos):
        app.register_blueprint(modulo.bp)
    return app
