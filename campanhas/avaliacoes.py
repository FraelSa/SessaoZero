"""
RF06 - avaliações de jogadores e mestres.

Regras:
- só avaliam e são avaliados os participantes de uma mesma campanha (o mestre
  e os jogadores inscritos), um a um, nunca a si mesmos;
- a avaliação abre depois que a primeira sessão aconteceu (a data da sessão
  já passou) ou quando a campanha está encerrada: ninguém avalia uma mesa em
  que ainda não jogou;
- cada pessoa dá uma nota a cada outra por campanha; avaliar de novo atualiza
  a nota e o comentário;
- a reputação de uma pessoa é a média das notas que recebeu, separada entre
  o que recebeu como mestre e como jogador.
"""

import datetime

from mongoengine.errors import NotUniqueError

from accounts.models import Usuario

from .models import Avaliacao

MOTIVO_AINDA_FECHADA = (
    "As avaliações abrem depois da primeira sessão. Para liberá-las, a "
    "campanha precisa ter a data da sessão definida."
)


def avaliacoes_abertas(campanha, agora=None):
    """True quando já dá para avaliar: a primeira sessão já passou ou a
    campanha foi encerrada. `data_sessao` é a data da PRIMEIRA sessão, mesmo
    nas campanhas recorrentes."""
    if campanha.status == "encerrada":
        return True
    agora = agora or datetime.datetime.utcnow()
    return campanha.data_sessao is not None and campanha.data_sessao <= agora


def participantes(campanha):
    """Mestre e jogadores inscritos, como lista de dicts
    {"email", "username", "papel"}, mestre primeiro."""
    gente = [
        {"email": campanha.mestre_email, "username": campanha.mestre_username, "papel": "mestre"}
    ]
    emails = list(campanha.jogadores_inscritos_emails)
    nomes = {
        u.email: u.username
        for u in Usuario.objects(email__in=emails).only("email", "username")
    }
    for email in emails:
        if email in nomes:
            gente.append({"email": email, "username": nomes[email], "papel": "jogador"})
    return gente


def alvos_do_usuario(campanha, usuario):
    """Quem `usuario` pode avaliar nesta campanha, cada um com a avaliação que
    ele já deu (ou None). Lista vazia se ele não participa da campanha."""
    todos = participantes(campanha)
    if usuario.email not in {p["email"] for p in todos}:
        return []

    minhas = {
        a.avaliado_email: a
        for a in Avaliacao.objects(
            campanha_id=str(campanha.id), avaliador_email=usuario.email
        )
    }
    return [
        {**p, "minha": minhas.get(p["email"])}
        for p in todos
        if p["email"] != usuario.email
    ]


def salvar_avaliacao(campanha, avaliador, username_avaliado, nota, comentario=""):
    """Cria (ou atualiza) a avaliação de `avaliador` sobre `username_avaliado`.

    Devolve (avaliacao, criada). Levanta ValueError, com a mensagem pronta
    para mostrar à pessoa, se a avaliação não é permitida."""
    if not avaliacoes_abertas(campanha):
        raise ValueError(MOTIVO_AINDA_FECHADA)

    gente = {p["username"]: p for p in participantes(campanha)}
    if avaliador.email not in {p["email"] for p in gente.values()}:
        raise ValueError("Só quem participa da campanha pode avaliar.")
    alvo = gente.get(username_avaliado)
    if alvo is None:
        raise ValueError("Essa pessoa não participa desta campanha.")
    if alvo["email"] == avaliador.email:
        raise ValueError("Você não pode avaliar a si mesmo.")

    chaves = dict(
        campanha_id=str(campanha.id),
        avaliador_email=avaliador.email,
        avaliado_email=alvo["email"],
    )

    def atualizar(existente):
        existente.nota = nota
        existente.comentario = comentario
        existente.atualizado_em = datetime.datetime.utcnow()
        existente.save()
        return existente

    existente = Avaliacao.objects(**chaves).first()
    if existente is not None:
        return atualizar(existente), False

    avaliacao = Avaliacao(
        **chaves,
        campanha_titulo=campanha.titulo,
        avaliador_username=avaliador.username,
        avaliado_username=alvo["username"],
        papel_avaliado=alvo["papel"],
        nota=nota,
        comentario=comentario,
    )
    try:
        avaliacao.save()
    except NotUniqueError:
        # Dois envios ao mesmo tempo: o outro chegou primeiro.
        return atualizar(Avaliacao.objects(**chaves).first()), False
    return avaliacao, True


def reputacao(email, papel=None):
    """{"media": 4.5 ou None, "total": n} das notas recebidas por `email`,
    como `papel` ("mestre" ou "jogador") ou em geral."""
    filtro = {"avaliado_email": email}
    if papel:
        filtro["papel_avaliado"] = papel
    notas = list(Avaliacao.objects(**filtro).scalar("nota"))
    if not notas:
        return {"media": None, "total": 0}
    return {"media": round(sum(notas) / len(notas), 1), "total": len(notas)}


def avaliacoes_recebidas(email, limite=20):
    """As avaliações mais recentes que `email` recebeu, para o perfil público."""
    return list(Avaliacao.objects(avaliado_email=email).order_by("-criado_em")[:limite])
