"""
As datas de criação (comentários, mensagens de chat, notificações) são
gravadas no MongoDB em UTC, sem fuso (datetime.utcnow). Para mostrar o
horário certo ao usuário (America/Bahia, definido em TIME_ZONE), convertemos
na hora de exibir.

Atenção: `Campanha.data_sessao` NÃO passa por aqui — essa data é digitada
pelo mestre já no horário dele e é guardada como foi digitada.
"""

import datetime

from django.utils import timezone


def para_horario_local(valor):
    if valor is None:
        return None
    if timezone.is_naive(valor):
        valor = timezone.make_aware(valor, datetime.timezone.utc)
    return timezone.localtime(valor)
