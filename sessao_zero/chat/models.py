"""
Chat em tempo real por campanha, citado no artigo do TCC ("uma sessão de
comentários e um chat que permita conversas e resoluções de dúvidas
quanto aos jogos"). Cada mensagem é salva no MongoDB (assim o histórico
sobrevive a reconexões e fica disponível para quem entra depois), e o
tempo real é feito com WebSockets (Django Channels) em chat/consumers.py.
"""

import datetime

from mongoengine import DateTimeField, Document, StringField


class MensagemChat(Document):
    campanha_id = StringField(required=True)

    autor_email = StringField(required=True)
    autor_username = StringField(required=True)
    texto = StringField(required=True, max_length=1000)

    criado_em = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "mensagens_chat",
        "indexes": ["campanha_id", "criado_em"],
        "ordering": ["criado_em"],
    }

    def __str__(self):
        return f"[{self.campanha_id}] {self.autor_username}: {self.texto[:30]}"
