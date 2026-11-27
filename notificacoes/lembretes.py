"""
RF08 - lembretes de sessão.

"O sistema deve notificar usuários sobre datas ou mudanças em campanhas e
sessões": as mudanças já geram avisos na hora (campanhas/views.py); aqui ficam
os avisos de DATA. Quando a próxima sessão de uma campanha está a menos de
`ANTECEDENCIA` de acontecer, o mestre e os jogadores inscritos recebem um
lembrete, pelo sininho do site e, se a pessoa não desligou, por e-mail.

Quem chama `enviar_lembretes` é um agendador externo, de hora em hora: o
comando `enviar_lembretes_sessao` ou o endereço protegido por token em
notificacoes/views.py. O plano gratuito do Render não tem cron.

Regras:
- campanhas encerradas ou sem data de sessão não geram lembrete;
- cada sessão é lembrada uma vez só: a data lembrada fica gravada na campanha
  (`lembrete_enviado_para`), então chamar a função de novo é inofensivo, e uma
  sessão remarcada (data nova) volta a ser lembrada;
- nas campanhas recorrentes vale a próxima ocorrência (RD04), e cada uma
  recebe o seu lembrete;
- o horário no texto vem no fuso de cada pessoa (Preferências).
"""

import datetime

from django.urls import reverse

from accounts.models import Usuario
from campanhas.models import Campanha
from core.horario import (
    FUSO_PADRAO,
    IDS_FUSOS,
    UTC,
    proxima_ocorrencia,
    rotulo_fuso,
    zona_segura,
)

from .servicos import notificar

ANTECEDENCIA = datetime.timedelta(hours=24)


def _quando(sessao_utc, nome_fuso):
    """'28/11/2026 às 21:00 (Salvador, Bahia)', no fuso da pessoa."""
    nome = nome_fuso if nome_fuso in IDS_FUSOS else FUSO_PADRAO
    local = sessao_utc.replace(tzinfo=UTC).astimezone(zona_segura(nome))
    return f"{local:%d/%m/%Y} às {local:%H:%M} ({rotulo_fuso(nome)})"


def _destinatarios(campanha):
    """E-mails de quem recebe o lembrete (o mestre e os inscritos), sem repetir."""
    return list(dict.fromkeys([campanha.mestre_email, *campanha.jogadores_inscritos_emails]))


def enviar_lembretes(agora=None, antecedencia=ANTECEDENCIA, simular=False, em_segundo_plano=True):
    """Envia os lembretes das sessões que começam dentro de `antecedencia`.

    Devolve uma lista com um item por campanha lembrada:
    {"titulo": ..., "sessao": data UTC da sessão, "avisos": quantas pessoas}.
    Com `simular=True` só calcula a lista: não avisa ninguém nem grava nada.
    Com `em_segundo_plano=False`, os e-mails saem antes de a função voltar.
    """
    agora = agora or datetime.datetime.utcnow()
    limite = agora + antecedencia
    lembradas = []

    candidatas = Campanha.objects(status__ne="encerrada", data_sessao__ne=None)
    for campanha in candidatas:
        sessao = proxima_ocorrencia(
            campanha.data_sessao, campanha.recorrencia, campanha.fuso_mestre, agora
        )
        if sessao is None or not (agora < sessao <= limite):
            continue
        if campanha.lembrete_enviado_para == sessao:
            continue

        emails = _destinatarios(campanha)
        if not simular:
            # Reserva a sessão antes de avisar: se duas chamadas se cruzarem
            # (dois cliques do agendador, dois processos), só uma passa daqui.
            reservada = Campanha.objects(
                id=campanha.id, lembrete_enviado_para__ne=sessao
            ).update_one(set__lembrete_enviado_para=sessao)
            if not reservada:
                continue

            fusos = {
                u.email: u.fuso_horario
                for u in Usuario.objects(email__in=emails).only("email", "fuso_horario")
            }
            url = reverse("detalhe_campanha", args=[campanha.id])
            for email in emails:
                quando = _quando(sessao, fusos.get(email))
                notificar(
                    email,
                    f'Lembrete: a sessão de "{campanha.titulo}" acontece em {quando}.',
                    url=url,
                    em_segundo_plano=em_segundo_plano,
                )

        lembradas.append({"titulo": campanha.titulo, "sessao": sessao, "avisos": len(emails)})

    return lembradas
