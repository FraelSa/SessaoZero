"""
RNF04 - "moderação em tempo real de conteúdos enviados para proteção e
segurança dos usuários". Toda vez que a moderação bloqueia um texto (ver
filtros.py), guardamos um registro aqui — serve tanto de auditoria (dá
pra revisar depois se o filtro está bom demais/de menos) quanto de base
para, no futuro, identificar usuários que insistem em burlar as regras.
"""

import datetime

from mongoengine import DateTimeField, Document, StringField


class ConteudoBloqueado(Document):
    autor_email = StringField(required=True)
    texto_original = StringField(required=True, max_length=1000)
    motivo = StringField(required=True)
    # Ex.: "chat:<campanha_id>" ou "comentario:<campanha_id>" — de onde
    # veio a tentativa de envio.
    origem = StringField(required=True)

    criado_em = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "conteudo_bloqueado",
        "indexes": ["autor_email", "-criado_em"],
        "ordering": ["-criado_em"],
    }

    def __str__(self):
        return f"[{self.origem}] {self.autor_email}: {self.motivo}"
