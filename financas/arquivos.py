"""Upload e download de comprovantes e fotos das caixinhas."""
import os
import uuid

from flask import Blueprint, current_app, send_from_directory
from werkzeug.utils import secure_filename

from .auth import login_required

EXTENSOES_COMPROVANTE = {"pdf", "jpg", "jpeg", "png", "webp"}
EXTENSOES_FOTO = {"jpg", "jpeg", "png", "webp", "gif"}

bp = Blueprint("arquivos", __name__, url_prefix="/arquivos")


def _salvar(arquivo, pasta, extensoes):
    """Salva o upload com nome único e retorna o nome do arquivo, ou None se vazio/extensão inválida."""
    if not arquivo or not arquivo.filename:
        return None
    extensao = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if extensao not in extensoes:
        return None
    nome = f"{uuid.uuid4().hex}_{secure_filename(arquivo.filename)}"
    os.makedirs(pasta, exist_ok=True)
    arquivo.save(os.path.join(pasta, nome))
    return nome


def salvar_comprovante(arquivo):
    return _salvar(arquivo, current_app.config["PASTA_COMPROVANTES"], EXTENSOES_COMPROVANTE)


def salvar_foto(arquivo):
    return _salvar(arquivo, current_app.config["PASTA_FOTOS"], EXTENSOES_FOTO)


@bp.route("/comprovantes/<path:nome>")
@login_required
def comprovante(nome):
    return send_from_directory(current_app.config["PASTA_COMPROVANTES"], nome)


@bp.route("/fotos/<path:nome>")
@login_required
def foto(nome):
    return send_from_directory(current_app.config["PASTA_FOTOS"], nome)
