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


# RNF05 - os comentários ficam dentro do documento da campanha (o MongoDB aceita
# 16 MB por documento) e a página os carrega junto: o limite mantém os dois sob controle.
MAX_COMENTARIOS = 1000


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
        "indexes": [
            "mestre_email",
            "sistema_rpg",
            "status",
            # A lista pública ordena por data (e o desempate pelo id mantém as
            # páginas estáveis); "Minhas inscrições" e a recomendação buscam pelo
            # e-mail dentro da lista de inscritos.
            {"fields": ["-criado_em", "-id"]},
            {"fields": ["status", "-criado_em"]},
            "jogadores_inscritos_emails",
        ],
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
        e a pessoa não estiver dentro.

        RNF05 - a conferência que vale é a do banco, numa operação só: com muita
        gente na página ao mesmo tempo, duas pessoas pedem a última vaga vendo a
        mesma lista; uma lista regravada inteira perderia uma das inscrições, ou
        passaria da lotação. Aqui o banco só acrescenta a pessoa se ela ainda não
        estiver dentro, a mesa não estiver encerrada e a posição da última vaga
        continuar vazia."""
        if email_jogador in self.jogadores_inscritos_emails:
            return False, "Você já está inscrito nesta campanha."
        if self.status == "encerrada":
            return False, "Esta campanha está encerrada e não aceita novas inscrições."
        if self.vagas_livres <= 0:
            return False, "Não há vagas livres nesta campanha."

        inscreveu = Campanha.objects(
            id=self.id,
            status__ne="encerrada",
            jogadores_inscritos_emails__ne=email_jogador,
            **{f"jogadores_inscritos_emails__{self.max_jogadores - 1}__exists": False},
        ).update_one(push__jogadores_inscritos_emails=email_jogador)

        if not inscreveu:
            # Alguém passou na frente (ou a mesa mudou) desde que esta cópia foi lida.
            self.reload("jogadores_inscritos_emails", "status")
            if email_jogador in self.jogadores_inscritos_emails:
                return False, "Você já está inscrito nesta campanha."
            if self.status == "encerrada":
                return False, "Esta campanha está encerrada e não aceita novas inscrições."
            return False, "Não há vagas livres nesta campanha."

        self._acompanhar_vagas()
        return True, "Inscrição realizada com sucesso."

    def remover_jogador(self, email_jogador):
        """RF07 - cancela a inscrição: a vaga volta a ficar livre e uma mesa
        lotada reabre. Numa mesa encerrada o status continua encerrado.
        (Também atômico, pelo mesmo motivo de `inscrever_jogador`.)"""
        removeu = Campanha.objects(
            id=self.id, jogadores_inscritos_emails=email_jogador
        ).update_one(pull__jogadores_inscritos_emails=email_jogador)
        if not removeu:
            self.reload("jogadores_inscritos_emails", "status")
            return False, "Você não está inscrito nesta campanha."

        self._acompanhar_vagas()
        return True, "Inscrição cancelada."

    def _acompanhar_vagas(self):
        """Faz o status seguir as vagas depois de uma entrada ou saída: lotada
        quando a última cadeira foi ocupada, aberta quando uma vaga reapareceu.
        Cada troca só vale se o banco ainda estiver no estado que a justifica, então
        entradas e saídas simultâneas chegam ao mesmo resultado em qualquer ordem.
        Mesa encerrada fica como está."""
        ultima = f"jogadores_inscritos_emails__{self.max_jogadores - 1}__exists"
        Campanha.objects(id=self.id, status="aberta", **{ultima: True}).update_one(
            set__status="lotada"
        )
        Campanha.objects(id=self.id, status="lotada", **{ultima: False}).update_one(
            set__status="aberta"
        )
        self.reload("jogadores_inscritos_emails", "status")

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
        """RF09 - comentários para conversas e dúvidas sobre a campanha.

        RNF05 - o comentário é acrescentado pelo próprio banco (e não gravando de
        novo a lista toda, o que perderia comentários feitos ao mesmo tempo). Como
        os comentários ficam dentro do documento da campanha, há um limite de
        MAX_COMENTARIOS por campanha; passando dele, devolve None."""
        comentario = Comentario(
            autor_email=autor_email, autor_username=autor_username, texto=texto
        )
        gravou = Campanha.objects(
            id=self.id, **{f"comentarios__{MAX_COMENTARIOS - 1}__exists": False}
        ).update_one(push__comentarios=comentario)
        return comentario if gravou else None

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
