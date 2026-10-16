"""
RNF04 - moderação em tempo real de conteúdo enviado por usuários (chat e
comentários das campanhas).

Esta é uma implementação simples, por palavras-chave e alguns padrões
(spam de links, texto todo em caixa alta), pensada para o escopo do TCC.
A lista TERMOS_PROIBIDOS abaixo é só um exemplo pequeno — em produção,
o recomendado é:

  a) manter uma lista bem mais completa e curada (idealmente revisada
     por alguém responsável pela comunidade), e/ou
  b) usar um serviço externo especializado em detectar discurso de ódio,
     assédio e toxicidade (ex.: a Perspective API do Google, ou um
     modelo de classificação de texto treinado para isso).

O resto do sistema só depende da função `moderar_texto`, então trocar a
implementação por (a) ou (b) no futuro não exige mudar chat/ nem
campanhas/ — só este arquivo.
"""

import re

# Lista de exemplo — cada projeto deve adaptar de acordo com as regras da
# própria comunidade. Mantida deliberadamente pequena e "óbvia" aqui.
TERMOS_PROIBIDOS = [
    "idiota",
    "imbecil",
    "burro",
    "burra",
]

PADRAO_LINK = re.compile(r"https?://")


def _contem_termo_proibido(texto_lower):
    for termo in TERMOS_PROIBIDOS:
        if termo in texto_lower:
            return True
    return False


def _eh_grito(texto):
    """Texto digitado quase todo em caixa alta - geralmente é grosseria
    ou spam chamando atenção."""
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 8:
        return False
    proporcao_maiusculas = sum(1 for c in letras if c.isupper()) / len(letras)
    return proporcao_maiusculas > 0.7


def _eh_spam_de_links(texto):
    return len(PADRAO_LINK.findall(texto)) > 1


def moderar_texto(texto):
    """
    Verifica um texto (mensagem de chat ou comentário) antes de ele ser
    salvo/distribuído aos outros usuários.

    Retorna uma tupla (aceito: bool, motivo: str). Quando aceito é False,
    `motivo` é uma mensagem pronta para mostrar ao usuário que tentou
    enviar o conteúdo.
    """
    texto_lower = texto.lower()

    if _contem_termo_proibido(texto_lower):
        return False, "Sua mensagem contém um termo não permitido na Sessão Zero."

    if _eh_grito(texto):
        return False, "Evite escrever tudo em maiúsculas — parece grosseria."

    if _eh_spam_de_links(texto):
        return False, "Muitos links em uma única mensagem — parece spam."

    return True, ""
