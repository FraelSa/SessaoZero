"""Busca por palavra-chave na listagem de campanhas.

Cada palavra digitada precisa aparecer em pelo menos um destes campos: título,
sinopse, sistema de RPG ou nome do mestre. Várias palavras se combinam com E
("strahd terror" só acha campanhas que têm as duas). A comparação ignora
maiúsculas e acentos: "acao" acha "Ação" e "sao paulo" acha "São Paulo".
"""

import re
import unicodedata

from mongoengine import Q

CAMPOS_BUSCA = ("titulo", "sinopse", "sistema_rpg", "mestre_username")

# Limites para que uma busca enorme não vire uma consulta enorme.
MAX_CARACTERES = 100
MAX_PALAVRAS = 6

# Letras que o MongoDB não trata como iguais ao comparar texto: cada uma vira
# uma classe com as variantes acentuadas, já nas duas caixas.
_VARIANTES = {
    "a": "àáâãäå",
    "e": "èéêë",
    "i": "ìíîï",
    "o": "òóôõö",
    "u": "ùúûü",
    "c": "ç",
    "n": "ñ",
}


def _sem_acento(texto):
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def palavras_da_busca(texto):
    """Palavras da busca, sem acento, em minúsculas e sem repetição."""
    texto = _sem_acento((texto or "")[:MAX_CARACTERES]).lower()
    palavras = []
    for palavra in texto.split():
        if palavra not in palavras:
            palavras.append(palavra)
    return palavras[:MAX_PALAVRAS]


def _regex_da_palavra(palavra):
    partes = []
    for letra in palavra:
        if letra in _VARIANTES:
            opcoes = letra + _VARIANTES[letra]
            partes.append(f"[{opcoes}{opcoes.upper()}]")
        else:
            partes.append(re.escape(letra))
    return "".join(partes)


def filtrar_por_palavras(campanhas, texto):
    """Devolve `campanhas` (um queryset) restrito às que casam com a busca.
    Sem palavras úteis, devolve o queryset como veio."""
    for palavra in palavras_da_busca(texto):
        padrao = _regex_da_palavra(palavra)
        em_algum_campo = Q()
        for campo in CAMPOS_BUSCA:
            em_algum_campo |= Q(**{f"{campo}__iregex": padrao})
        campanhas = campanhas.filter(em_algum_campo)
    return campanhas
