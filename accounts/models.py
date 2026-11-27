"""
Documento de Usuário da Sessão Zero, armazenado na coleção "usuarios" do
MongoDB.

Não usamos o model User padrão do Django (que vive no banco relacional)
porque o cadastro, login e perfil do usuário são dados de produto e devem
ficar no MongoDB, como definido no artigo do TCC. Em vez disso, o hash da
senha é feito com os mesmos utilitários que o Django usa por baixo dos
panos (django.contrib.auth.hashers), então a segurança (RNF02) é a mesma;
só a "tabela" onde o dado mora é que muda.
"""

import datetime

from django.contrib.auth.hashers import check_password, make_password
from mongoengine import (
    BinaryField,
    BooleanField,
    DateTimeField,
    DictField,
    Document,
    EmailField,
    IntField,
    StringField,
)

from core.horario import FUSO_PADRAO


class Usuario(Document):
    # RF01 - cadastro de usuários
    username = StringField(required=True, unique=True, max_length=30)
    email = EmailField(required=True, unique=True)
    senha_hash = StringField(required=True)

    bio = StringField(max_length=500, default="")
    avatar_url = StringField(default="")

    # Avatar: um dos desenhos prontos (accounts/avatares.py), ou a foto
    # enviada (guardada em FotoPerfil; `tem_foto` avisa que ela existe).
    # `avatar_versao` muda a cada troca, para o navegador não mostrar o
    # avatar antigo guardado em cache.
    avatar_preset = StringField(default="")
    tem_foto = BooleanField(default=False)
    avatar_versao = IntField(default=0)

    # RF05 - personalização de conteúdo. Guarda, por exemplo, os sistemas de
    # RPG e estilos de jogo que o usuário mais interage; é a partir daqui
    # que o algoritmo de recomendação (TF-IDF) vai montar o perfil dele.
    preferencias = DictField(default=dict)

    # RF04 - recuperação de conta
    token_recuperacao_senha = StringField(null=True)
    token_recuperacao_expira_em = DateTimeField(null=True)

    # Confirmação de e-mail no cadastro. O campo é "aguardando" (e não
    # "confirmado") de propósito: contas antigas, criadas antes desta
    # funcionalidade, não têm o campo no banco e assim continuam liberadas.
    aguardando_confirmacao = BooleanField(default=False)
    token_confirmacao = StringField(null=True)
    token_confirmacao_expira_em = DateTimeField(null=True)

    # RF01 - troca de e-mail. O endereço novo fica aqui, com um link de confirmação
    # enviado a ELE, até a pessoa confirmar; só então vira `email` (ver
    # accounts/identidade.py). Contas antigas, sem os campos, não têm pedido.
    novo_email = EmailField(null=True)
    token_novo_email = StringField(null=True)
    token_novo_email_expira_em = DateTimeField(null=True)

    # Receber um e-mail a cada notificação do sistema (editável em Preferências).
    notificar_por_email = BooleanField(default=True)

    # RD04 - fuso horário da pessoa (editável em Preferências). Datas e horas
    # aparecem convertidas para ele, e o horário que o mestre digita ao marcar
    # uma sessão vale nele. Contas antigas, sem o campo, ficam no padrão.
    fuso_horario = StringField(default=FUSO_PADRAO)

    # RNF03 - quando (UTC) e em qual versão a pessoa aceitou a Política de
    # Privacidade ao se cadastrar. Contas antigas não têm o registro.
    politica_aceita_em = DateTimeField(null=True)
    politica_versao = StringField(null=True)

    ativo = BooleanField(default=True)
    criado_em = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "usuarios",
        "indexes": ["email", "username"],
    }

    def set_senha(self, senha_em_texto_puro):
        """Gera e guarda o hash da senha (nunca a senha em texto puro)."""
        self.senha_hash = make_password(senha_em_texto_puro)

    def checar_senha(self, senha_em_texto_puro):
        """Usado no login (RF03) para validar e-mail + senha."""
        return check_password(senha_em_texto_puro, self.senha_hash)

    def __str__(self):
        return f"{self.username} <{self.email}>"


class FotoPerfil(Document):
    """Foto enviada pelo usuário, já recortada e reduzida (ver imagens.py).
    Fica em uma coleção própria para que os bytes da imagem não sejam
    carregados toda vez que o Usuario é lido (o que acontece em toda página)."""

    usuario_id = StringField(required=True, unique=True)
    dados = BinaryField(required=True, max_bytes=300_000)
    atualizado_em = DateTimeField(default=datetime.datetime.utcnow)

    meta = {"collection": "fotos_perfil"}


class CadastroPendente(Document):
    """Cadastro que ainda não foi confirmado por e-mail.

    A conta (documento em "usuarios") só passa a existir quando a pessoa
    clica no link enviado por e-mail. Até lá, os dados do cadastro ficam
    aqui, em uma coleção separada, e o MongoDB apaga sozinho cada registro
    quando `expira_em` passa (índice TTL). A senha já fica guardada como
    hash, nunca em texto puro.
    """

    username = StringField(required=True, max_length=30)
    email = EmailField(required=True)
    senha_hash = StringField(required=True)

    token = StringField(required=True, unique=True)
    criado_em = DateTimeField(default=datetime.datetime.utcnow)
    # RNF03 - aceite da Política de Privacidade (passa para o Usuario quando
    # o e-mail é confirmado).
    politica_aceita_em = DateTimeField(null=True)
    # Usado para limitar o reenvio do e-mail (evita disparar e-mails em série).
    ultimo_envio_em = DateTimeField(default=datetime.datetime.utcnow)
    expira_em = DateTimeField(required=True)

    meta = {
        "collection": "cadastros_pendentes",
        "indexes": [
            "email",
            {"fields": ["expira_em"], "expireAfterSeconds": 0},
        ],
    }
