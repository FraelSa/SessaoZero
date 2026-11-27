"""
Apoio aos testes automatizados (python manage.py test).

Os testes NUNCA usam o MongoDB real: `MongoTestCase` troca a conexão criada em
settings.py por um MongoDB simulado em memória (biblioteca mongomock, em
requirements-dev.txt). Assim dá para rodar os testes com o .env apontando para
o Atlas sem tocar em nenhum dado.
"""

import re

import mongomock
from django.conf import settings
from django.core import mail
from django.test import TestCase
from mongoengine import connect, disconnect

from accounts.models import CadastroPendente, FotoPerfil, TentativaLogin, Usuario
from campanhas.models import Avaliacao, Campanha
from chat.models import MensagemChat
from moderacao.models import ConteudoBloqueado
from notificacoes.models import Notificacao

DOCUMENTOS = (
    Usuario,
    FotoPerfil,
    CadastroPendente,
    TentativaLogin,
    Campanha,
    Avaliacao,
    MensagemChat,
    ConteudoBloqueado,
    Notificacao,
)

SENHA_PADRAO = "Senha-forte-123"


class MongoTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        disconnect()  # solta a conexão criada por settings.py
        connect(
            "sessao_zero_teste",
            host="mongodb://localhost",
            mongo_client_class=mongomock.MongoClient,
        )
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        disconnect()

    def setUp(self):
        for documento in DOCUMENTOS:
            documento.drop_collection()

    # -- atalhos ------------------------------------------------------------

    def criar_usuario(self, username="ana", email=None, senha=SENHA_PADRAO, **extras):
        extras.setdefault("notificar_por_email", False)  # os testes não enviam e-mail
        usuario = Usuario(username=username, email=email or f"{username}@exemplo.com", **extras)
        usuario.set_senha(senha)
        usuario.save()
        return usuario

    def entrar(self, usuario):
        sessao = self.client.session
        sessao["usuario_id"] = str(usuario.id)
        sessao["sessao_versao"] = usuario.sessao_versao or 0
        sessao.save()
        # A sessão fica num cookie assinado (SESSION_ENGINE em settings.py):
        # depois de salvar, o conteúdo novo só chega ao site pelo cookie.
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key

    def criar_campanha(self, mestre, **extras):
        dados = dict(
            titulo="A Maldição de Strahd",
            sinopse="Terror gótico para iniciantes.",
            sistema_rpg="D&D 5e",
            classificacao="14",
            max_jogadores=3,
            mestre_email=mestre.email,
            mestre_username=mestre.username,
        )
        dados.update(extras)
        campanha = Campanha(**dados)
        campanha.save()
        return campanha

    def textos_das_notificacoes(self, usuario):
        return [n.texto for n in Notificacao.objects(destinatario_email=usuario.email)]

    def token_do_email(self, rota, indice=-1):
        """Código secreto do link `/contas/<rota>/<token>/` num dos e-mails
        enviados (por padrão, o último). O banco só guarda o resumo do código,
        então é do e-mail que o teste precisa tirá-lo."""
        corpo = mail.outbox[indice].body
        return re.search(rf"/contas/{re.escape(rota)}/([^/\s]+)/", corpo).group(1)
