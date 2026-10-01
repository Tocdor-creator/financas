"""Taxas públicas do Banco Central (API SGS), com cache em memória."""
import json
import time
import urllib.request

SERIE_SELIC = 432    # meta Selic, % ao ano
SERIE_CDI = 4389     # CDI anualizado, % ao ano
VALIDADE_CACHE = 6 * 3600

_cache = {}


def _buscar(serie):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json"
    try:
        with urllib.request.urlopen(url, timeout=3) as resposta:
            dados = json.loads(resposta.read().decode())
        return dados[0] if dados else None  # {"data": "dd/mm/aaaa", "valor": "13.75"}
    except Exception:
        return None  # sem internet ou API fora do ar: a tela só não mostra a taxa


def taxa(serie):
    salvo = _cache.get(serie)
    if salvo and time.monotonic() - salvo[0] < VALIDADE_CACHE:
        return salvo[1]
    valor = _buscar(serie)
    _cache[serie] = (time.monotonic(), valor)
    return valor
