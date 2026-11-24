"""
Documentos de Campanha/Sessão de RPG, armazenados na coleção "campanhas".

Cada Campanha guarda uma lista embutida de Comentario (RF08) e a lista de
e-mails dos jogadores inscritos (RF06), seguindo o modelo orientado a
documentos do MongoDB descrito no artigo, em vez de tabelas separadas com
JOINs como seria em um banco relacional.
"""

import datetime

from mongoengine import (
    DateTimeField,
    Document,
    EmbeddedDocument,
    EmbeddedDocumentListField,
    IntField,
    ListField,
    StringField,
)

SISTEMAS_RPG_COMUNS = (
    "D&D 5e",
    "Pathfinder 2e",
    "Tormenta20",
    "Ordem Paranormal",
    "Call of Cthulhu",
    "Vampiro: A Máscara",
    "Old Dragon",
    "3D&T Victory",
    "Cyberpunk RED",
    "Shadowrun",
    "Savage Worlds",
    "Daggerheart",
    "Outro",
)

STATUS_CAMPANHA = ("aberta", "lotada", "encerrada")


class Comentario(EmbeddedDocument):
    # RF08 - seção de comentários em cada postagem/campanha
    autor_email = StringField(required=True)
    autor_username = StringField(required=True)
    texto = StringField(required=True, max_length=1000)
    criado_em = DateTimeField(default=datetime.datetime.utcnow)


class Campanha(Document):
    # RF02 - criar, editar e excluir campanhas/sessões
    titulo = StringField(required=True, max_length=120)
    sinopse = StringField(required=True, max_length=3000)
    sistema_rpg = StringField(required=True, choices=SISTEMAS_RPG_COMUNS)

    mestre_email = StringField(required=True)
    mestre_username = StringField(required=True)

    # RF07 - guarda a data marcada para a próxima sessão, para poder
    # notificar os jogadores quando ela for definida ou mudar.
    data_sessao = DateTimeField(null=True)

    max_jogadores = IntField(required=True, min_value=1)
    # RF06 - inscrição de jogadores interessados, de acordo com vagas livres
    jogadores_inscritos_emails = ListField(StringField(), default=list)

    status = StringField(choices=STATUS_CAMPANHA, default="aberta")

    comentarios = EmbeddedDocumentListField(Comentario, default=list)

    criado_em = DateTimeField(default=datetime.datetime.utcnow)
    atualizado_em = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "campanhas",
        "indexes": ["mestre_email", "sistema_rpg", "status"],
        "ordering": ["-criado_em"],
    }

    @property
    def vagas_livres(self):
        return max(self.max_jogadores - len(self.jogadores_inscritos_emails), 0)

    @property
    def assentos(self):
        """Uma entrada por vaga (True = ocupada, False = livre); usada nos
        templates para desenhar as cadeiras da mesa."""
        ocupadas = min(len(self.jogadores_inscritos_emails), self.max_jogadores)
        return [True] * ocupadas + [False] * (self.max_jogadores - ocupadas)

    def inscrever_jogador(self, email_jogador):
        """RF06 - só inscreve se ainda houver vaga e a pessoa não estiver dentro."""
        if email_jogador in self.jogadores_inscritos_emails:
            return False, "Você já está inscrito nesta campanha."
        if self.vagas_livres <= 0:
            return False, "Não há vagas livres nesta campanha."
        self.jogadores_inscritos_emails.append(email_jogador)
        if self.vagas_livres == 0:
            self.status = "lotada"
        self.save()
        return True, "Inscrição realizada com sucesso."

    def adicionar_comentario(self, autor_email, autor_username, texto):
        """RF08 - comentários para conversas e dúvidas sobre a campanha."""
        comentario = Comentario(
            autor_email=autor_email, autor_username=autor_username, texto=texto
        )
        self.comentarios.append(comentario)
        self.save()
        return comentario

    def __str__(self):
        return f"{self.titulo} ({self.sistema_rpg})"
