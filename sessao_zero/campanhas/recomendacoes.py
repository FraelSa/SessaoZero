"""
RF05 - "o sistema deve personalizar o conteúdo visualizado de acordo com as
preferências do usuário", usando TF-IDF (Term Frequency-Inverse Document
Frequency), como citado no artigo do TCC a partir de [Silva 2026].

Como funciona, em resumo:

1. Cada campanha vira um "documento" de texto: sistema de RPG + título +
   sinopse (o sistema é repetido para pesar mais na comparação).
2. O perfil do usuário também vira um "documento" de texto, montado a
   partir das preferências explícitas que ele cadastrou (RF05) e do
   histórico implícito de campanhas que ele já mestrou ou já jogou.
3. Colocamos o documento do usuário e o de todas as campanhas candidatas
   na mesma matriz TF-IDF e comparamos o vetor do usuário com o de cada
   campanha usando similaridade de cosseno.
4. As campanhas mais parecidas aparecem primeiro.

Essa abordagem é baseada em conteúdo (content-based), então funciona
mesmo sem "histórico colaborativo" — ou seja, sem precisar de dados de
outros usuários, o que é importante numa rede social nova, com poucos
usuários ainda. Sem preferências nem histórico, cai num fallback simples
(campanhas mais recentes com vaga).
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .models import Campanha

# Peso extra para o sistema de RPG: ele é o atributo mais forte de "isso é
# parecido com o que eu gosto" (jogar D&D nada tem a ver com Call of
# Cthulhu, mesmo que as sinopses usem palavras parecidas).
PESO_SISTEMA_RPG = 3


def _texto_da_campanha(campanha):
    partes = [campanha.sistema_rpg] * PESO_SISTEMA_RPG + [
        campanha.titulo,
        campanha.sinopse,
    ]
    return " ".join(partes)


def _texto_do_perfil(usuario):
    partes = []

    # Preferências explícitas (RF05), cadastradas em /contas/preferencias/
    preferencias = usuario.preferencias or {}
    for valor in preferencias.values():
        if isinstance(valor, (list, tuple, set)):
            partes.extend(str(item) for item in valor)
        elif valor:
            partes.append(str(valor))

    # Histórico implícito: campanhas que o usuário mestra...
    for campanha in Campanha.objects(mestre_email=usuario.email):
        partes.append(_texto_da_campanha(campanha))

    # ...e campanhas em que ele está inscrito como jogador.
    for campanha in Campanha.objects(jogadores_inscritos_emails=usuario.email):
        partes.append(_texto_da_campanha(campanha))

    return " ".join(partes)


def recomendar_campanhas(usuario, limite=5):
    """
    Retorna até `limite` campanhas abertas, da mais para a menos parecida
    com o perfil do usuário. Não recomenda campanhas que ele já mestra ou
    em que já está inscrito.
    """
    candidatas = list(
        Campanha.objects(status="aberta")
        .filter(mestre_email__ne=usuario.email)
        .filter(jogadores_inscritos_emails__ne=usuario.email)
    )

    if not candidatas:
        return []

    perfil_texto = _texto_do_perfil(usuario)

    if not perfil_texto.strip():
        # Sem preferências nem histórico ainda: não tem o que comparar por
        # TF-IDF, então mostra as campanhas mais recentes em vez de uma
        # tela vazia.
        candidatas.sort(key=lambda campanha: campanha.criado_em, reverse=True)
        return candidatas[:limite]

    documentos = [perfil_texto] + [_texto_da_campanha(c) for c in candidatas]

    vetorizador = TfidfVectorizer()
    matriz_tfidf = vetorizador.fit_transform(documentos)

    vetor_usuario = matriz_tfidf[0:1]
    vetores_campanhas = matriz_tfidf[1:]
    similaridades = cosine_similarity(vetor_usuario, vetores_campanhas)[0]

    candidatas_ordenadas = [
        campanha
        for campanha, score in sorted(
            zip(candidatas, similaridades), key=lambda par: par[1], reverse=True
        )
    ]

    return candidatas_ordenadas[:limite]
