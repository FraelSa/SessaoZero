"""
RF07 - "o sistema deve notificar usuários de datas ou mudanças em
campanhas e sessões". Cada notificação é um documento simples na coleção
"notificacoes": para quem é, o texto, um link opcional (para levar direto
à campanha) e se já foi lida.

Notificações "empurradas" de verdade (push/e-mail/WebSocket) ficam fora do
escopo por enquanto — aqui elas são gravadas no banco e aparecem quando o
usuário abre a Sessão Zero, no estilo "sininho de notificações" comum em
redes sociais. Dá pra plugar um envio por e-mail (reaproveitando o
EMAIL_BACKEND já configurado para RF04) ou WebSockets (Django Channels)
depois, sem mudar esse modelo.
"""

import datetime

from mongoengine import BooleanField, DateTimeField, Document, StringField


class Notificacao(Document):
    destinatario_email = StringField(required=True)
    texto = StringField(required=True, max_length=300)
    url = StringField(default="")

    lida = BooleanField(default=False)
    criado_em = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "notificacoes",
        "indexes": ["destinatario_email", "-criado_em"],
        "ordering": ["-criado_em"],
    }

    def __str__(self):
        return f"Para {self.destinatario_email}: {self.texto}"
