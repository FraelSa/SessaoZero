"""
Documentos de Campanha/Sessão de RPG, armazenados na coleção "campanhas".

Cada Campanha guarda uma lista embutida de Comentario (RF09) e a lista de
e-mails dos jogadores inscritos (RF07), seguindo o modelo orientado a
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

from core.horario import FUSO_PADRAO, RECORRENCIAS, proxima_ocorrencia

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
    "Sistema Próprio",
)

# Opção para mesas com sistema criado pelo mestre (ou que não está na lista).
# Quem escolhe digita o nome, e é esse nome que fica gravado na campanha.
# Campanhas antigas podem ter "Outro", a opção que existia antes desta.
SISTEMA_PROPRIO = "Sistema Próprio"
SISTEMAS_DA_LISTA = tuple(s for s in SISTEMAS_RPG_COMUNS if s != SISTEMA_PROPRIO)
SISTEMA_NOME_MAX = 60

STATUS_CAMPANHA = ("aberta", "lotada", "encerrada")

# RD03 - classificação indicativa de conteúdo, definida pelo mestre: uma faixa
# etária e, opcionalmente, os temas sensíveis que a mesa pode abordar.
CLASSIFICACOES_INDICATIVAS = (
    ("livre", "Livre"),
    ("12", "12 anos"),
    ("14", "14 anos"),
    ("16", "16 anos"),
    ("18", "18 anos"),
)
TEMAS_SENSIVEIS = (
    ("violencia", "Violência"),
    ("terror", "Terror"),
    ("linguagem_forte", "Linguagem forte"),
    ("temas_adultos", "Temas adultos"),
    ("drogas", "Uso de drogas"),
)


class Comentario(EmbeddedDocument):
    # RF09 - seção de comentários em cada postagem/campanha
    autor_email = StringField(required=True)
    autor_username = StringField(required=True)
    texto = StringField(required=True, max_length=1000)
    criado_em = DateTimeField(default=datetime.datetime.utcnow)


class Campanha(Document):
    # RF02 - criar, editar e excluir campanhas/sessões
    titulo = StringField(required=True, max_length=120)
    sinopse = StringField(required=True, max_length=3000)
    # Um dos SISTEMAS_DA_LISTA ou o nome digitado para um sistema próprio.
    sistema_rpg = StringField(required=True, max_length=SISTEMA_NOME_MAX)

    # RD03 - classificação indicativa. É None nas campanhas criadas antes deste
    # campo existir; o mestre escolhe uma na próxima edição.
    classificacao = StringField(choices=CLASSIFICACOES_INDICATIVAS, null=True)
    temas_sensiveis = ListField(StringField(choices=TEMAS_SENSIVEIS), default=list)

    mestre_email = StringField(required=True)
    mestre_username = StringField(required=True)

    # RD04 - data e horário de uma sessão, gravados em UTC (sem fuso). Para
    # sessões que se repetem, é a âncora: a próxima sessão é calculada a partir
    # dela (ver `proxima_sessao`). Também serve para notificar (RF08) os
    # jogadores quando a data for definida ou mudar.
    data_sessao = DateTimeField(null=True)
    recorrencia = StringField(choices=RECORRENCIAS, default="unica")
    # Fuso em que o mestre marcou o horário; a recorrência mantém o horário
    # de relógio nele. Campanhas antigas foram marcadas em America/Bahia.
    fuso_mestre = StringField(default=FUSO_PADRAO)

    # RF08 - qual sessão (data em UTC sem fuso, a de `proxima_sessao`) já teve o
    # lembrete enviado. Evita avisar duas vezes a mesma sessão; como cada sessão
    # de uma campanha recorrente tem a sua data, ela volta a ser lembrada.
    lembrete_enviado_para = DateTimeField(null=True)

    max_jogadores = IntField(required=True, min_value=1)
    # RF07 - inscrição de jogadores interessados, de acordo com vagas livres
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
    def tem_sistema_proprio(self):
        return self.sistema_rpg not in SISTEMAS_DA_LISTA

    @property
    def vagas_livres(self):
        return max(self.max_jogadores - len(self.jogadores_inscritos_emails), 0)

    @property
    def assentos(self):
        """Uma entrada por vaga (True = ocupada, False = livre); usada nos
        templates para desenhar as cadeiras da mesa."""
        ocupadas = min(len(self.jogadores_inscritos_emails), self.max_jogadores)
        return [True] * ocupadas + [False] * (self.max_jogadores - ocupadas)

    @property
    def rotulo_classificacao(self):
        return dict(CLASSIFICACOES_INDICATIVAS).get(self.classificacao, "")

    @property
    def rotulos_temas(self):
        nomes = dict(TEMAS_SENSIVEIS)
        return [nomes[t] for t in (self.temas_sensiveis or []) if t in nomes]

    @property
    def rotulo_recorrencia(self):
        return dict(RECORRENCIAS).get(self.recorrencia, "")

    @property
    def proxima_sessao(self):
        """RD04 - data da próxima sessão, em UTC sem fuso. Numa campanha que se
        repete, avança sozinha a partir da data gravada; numa sessão única, é a
        própria data."""
        return proxima_ocorrencia(self.data_sessao, self.recorrencia, self.fuso_mestre)

    def sincronizar_status(self):
        """Mantém `status` coerente com as vagas: lotada quando não há vaga
        livre, aberta quando há. Campanhas encerradas ficam como estão."""
        if self.status == "encerrada":
            return
        self.status = "lotada" if self.vagas_livres == 0 else "aberta"

    def inscrever_jogador(self, email_jogador):
        """RF07 - só inscreve se a mesa não estiver encerrada, ainda houver vaga
        e a pessoa não estiver dentro."""
        if email_jogador in self.jogadores_inscritos_emails:
            return False, "Você já está inscrito nesta campanha."
        if self.status == "encerrada":
            return False, "Esta campanha está encerrada e não aceita novas inscrições."
        if self.vagas_livres <= 0:
            return False, "Não há vagas livres nesta campanha."
        self.jogadores_inscritos_emails.append(email_jogador)
        self.sincronizar_status()
        self.save()
        return True, "Inscrição realizada com sucesso."

    def remover_jogador(self, email_jogador):
        """RF07 - cancela a inscrição: a vaga volta a ficar livre e uma mesa
        lotada reabre. Numa mesa encerrada o status continua encerrado."""
        if email_jogador not in self.jogadores_inscritos_emails:
            return False, "Você não está inscrito nesta campanha."
        self.jogadores_inscritos_emails.remove(email_jogador)
        self.sincronizar_status()
        self.save()
        return True, "Inscrição cancelada."

    def encerrar(self):
        """RF02 - o mestre dá a mesa por encerrada: ela deixa de aceitar
        inscrições e as avaliações (RF06) abrem, mesmo sem data de sessão."""
        self.status = "encerrada"
        self.atualizado_em = datetime.datetime.utcnow()
        self.save()

    def reabrir(self):
        """RF02 - desfaz `encerrar`: o status volta a seguir as vagas (aberta,
        ou lotada se não sobrou vaga)."""
        self.status = "aberta"
        self.sincronizar_status()
        self.atualizado_em = datetime.datetime.utcnow()
        self.save()

    def adicionar_comentario(self, autor_email, autor_username, texto):
        """RF09 - comentários para conversas e dúvidas sobre a campanha."""
        comentario = Comentario(
            autor_email=autor_email, autor_username=autor_username, texto=texto
        )
        self.comentarios.append(comentario)
        self.save()
        return comentario

    def __str__(self):
        return f"{self.titulo} ({self.sistema_rpg})"


PAPEIS_AVALIADO = ("mestre", "jogador")

NOTAS = (1, 2, 3, 4, 5)


class Avaliacao(Document):
    """RF06 - nota de 1 a 5 (e um comentário opcional) que um participante dá a
    outro depois de jogar na mesma campanha, na coleção "avaliacoes".

    O título da campanha e os nomes de usuário são copiados para cá de
    propósito: excluir a campanha não apaga a reputação de ninguém, e a
    avaliação continua legível. Quando o AUTOR exclui a conta, a avaliação
    fica sem o nome dele; quando o AVALIADO exclui a conta, ela é apagada
    (ver accounts/exclusao.py).
    """

    campanha_id = StringField(required=True)
    campanha_titulo = StringField(required=True, max_length=120)

    avaliador_email = StringField(required=True)
    avaliador_username = StringField(required=True)

    avaliado_email = StringField(required=True)
    avaliado_username = StringField(required=True)
    # Papel que a pessoa avaliada tinha NESSA campanha: separa a reputação
    # como mestre da reputação como jogador.
    papel_avaliado = StringField(required=True, choices=PAPEIS_AVALIADO)

    nota = IntField(required=True, min_value=1, max_value=5)
    comentario = StringField(max_length=500, default="")

    criado_em = DateTimeField(default=datetime.datetime.utcnow)
    atualizado_em = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "avaliacoes",
        "indexes": [
            # Uma avaliação por par de pessoas em cada campanha (reenviar o
            # formulário atualiza a existente).
            {"fields": ["campanha_id", "avaliador_email", "avaliado_email"], "unique": True},
            "avaliado_email",
        ],
        "ordering": ["-criado_em"],
    }
