"""
RNF04 - "moderação em tempo real de conteúdos enviados para proteção e
segurança dos usuários". Toda vez que a moderação bloqueia um texto (ver
filtros.py), guardamos um registro aqui. Ele serve de auditoria (quem revisa vê
se o filtro está bom demais ou de menos, no painel de moderação) e de base para
identificar quem insiste em burlar as regras.

RNF03 - o registro guarda o texto e o e-mail de quem tentou enviar, então não
fica para sempre: o MongoDB o apaga sozinho depois de RETENCAO_DIAS (índice TTL).
"""

import datetime

from mongoengine import DateTimeField, Document, StringField

# Quanto tempo o registro de um texto barrado é guardado (informado na Política
# de Privacidade).
RETENCAO_DIAS = 180

DECISOES = (
    ("correto", "Bloqueio correto"),
    ("falso_positivo", "Falso positivo"),
)


class ConteudoBloqueado(Document):
    autor_email = StringField(required=True)
    texto_original = StringField(required=True, max_length=1000)
    motivo = StringField(required=True)
    # Ex.: "chat:<campanha_id>", "comentario:<campanha_id>", "perfil:bio",
    # "campanha:titulo" - de onde veio a tentativa de envio.
    origem = StringField(required=True)

    criado_em = DateTimeField(default=datetime.datetime.utcnow)

    # Revisão pelo painel de moderação. Registros antigos não têm estes campos
    # e contam como "ainda não revisados".
    revisado_em = DateTimeField(null=True)
    decisao = StringField(choices=DECISOES, null=True)
    revisado_por = StringField(null=True)

    meta = {
        "collection": "conteudo_bloqueado",
        "indexes": [
            "autor_email",
            {"fields": ["criado_em"], "expireAfterSeconds": RETENCAO_DIAS * 24 * 3600},
        ],
        "ordering": ["-criado_em"],
    }

    @property
    def revisado(self):
        return self.revisado_em is not None

    def __str__(self):
        return f"[{self.origem}] {self.autor_email}: {self.motivo}"
