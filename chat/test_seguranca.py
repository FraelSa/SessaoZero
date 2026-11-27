"""RNF02 / RNF04 / RNF05 - o chat respeita a sessão encerrada e o ritmo de envio."""

from unittest import mock

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from accounts.models import Usuario
from core.base_testes import MongoTestCase

from . import consumers
from .consumers import ChatConsumer
from .models import MensagemChat


def comunicador(campanha, usuario, versao=None):
    """Conexão WebSocket de `usuario`, com a sessão que o AuthMiddlewareStack
    preencheria em produção (`versao` é o número guardado no cookie)."""
    conexao = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{campanha.id}/")
    conexao.scope["url_route"] = {"kwargs": {"campanha_id": str(campanha.id)}}
    conexao.scope["session"] = {
        "usuario_id": str(usuario.id),
        "sessao_versao": usuario.sessao_versao if versao is None else versao,
    }
    return conexao


class RelogioFalso:
    """Substitui o módulo `time` só dentro do consumer (trocar `time.monotonic`
    de verdade pararia o relógio do próprio asyncio)."""

    def __init__(self):
        self.agora = 1000.0

    def monotonic(self):
        return self.agora


class SessaoEncerradaNoChatTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.jogador = self.criar_usuario("jogador")
        self.campanha = self.criar_campanha(
            self.mestre, jogadores_inscritos_emails=[self.jogador.email]
        )

    async def test_sessao_encerrada_nao_abre_o_chat(self):
        await sync_to_async(self.jogador.encerrar_sessoes)()
        await sync_to_async(self.jogador.save)()
        conexao = comunicador(self.campanha, self.jogador, versao=0)
        self.assertFalse((await conexao.connect())[0])

    async def test_sessao_antiga_sem_numero_ainda_abre_o_chat(self):
        conexao = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.campanha.id}/")
        conexao.scope["url_route"] = {"kwargs": {"campanha_id": str(self.campanha.id)}}
        conexao.scope["session"] = {"usuario_id": str(self.jogador.id)}
        self.assertTrue((await conexao.connect())[0])
        await conexao.disconnect()

    async def test_trocar_a_senha_com_o_chat_aberto_desconecta_no_proximo_envio(self):
        conexao = comunicador(self.campanha, self.jogador)
        do_mestre = comunicador(self.campanha, self.mestre)
        await conexao.connect()
        await do_mestre.connect()

        await sync_to_async(
            lambda: Usuario.objects(id=self.jogador.id).update_one(inc__sessao_versao=1)
        )()
        await conexao.send_json_to({"texto": "ainda posso falar?"})

        self.assertEqual((await conexao.receive_output())["type"], "websocket.close")
        self.assertEqual(await sync_to_async(MensagemChat.objects.count)(), 0)
        self.assertTrue(await do_mestre.receive_nothing())
        await do_mestre.disconnect()


class RitmoDeEnvioTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.jogador = self.criar_usuario("jogador")
        self.campanha = self.criar_campanha(
            self.mestre, jogadores_inscritos_emails=[self.jogador.email]
        )

    async def enviar(self, conexao, texto):
        await conexao.send_json_to({"texto": texto})
        return await conexao.receive_json_from()

    async def test_passando_do_limite_a_mensagem_e_recusada_e_nao_e_salva(self):
        conexao = comunicador(self.campanha, self.jogador)
        do_mestre = comunicador(self.campanha, self.mestre)
        await conexao.connect()
        await do_mestre.connect()

        for i in range(consumers.MAX_MENSAGENS_NA_JANELA):
            resposta = await self.enviar(conexao, f"mensagem {i}")
            self.assertEqual(resposta["texto"], f"mensagem {i}")
            await do_mestre.receive_json_from()

        resposta = await self.enviar(conexao, "mais uma")
        self.assertEqual(resposta["tipo"], "erro")
        self.assertIn("rápido demais", resposta["motivo"])
        self.assertEqual(
            await sync_to_async(MensagemChat.objects.count)(), consumers.MAX_MENSAGENS_NA_JANELA
        )
        self.assertTrue(await do_mestre.receive_nothing())

        await conexao.disconnect()
        await do_mestre.disconnect()

    async def test_o_limite_vale_por_conexao_e_nao_atrapalha_os_outros(self):
        do_jogador = comunicador(self.campanha, self.jogador)
        do_mestre = comunicador(self.campanha, self.mestre)
        await do_jogador.connect()
        await do_mestre.connect()

        for i in range(consumers.MAX_MENSAGENS_NA_JANELA + 1):
            await do_jogador.send_json_to({"texto": f"spam {i}"})
        for _ in range(consumers.MAX_MENSAGENS_NA_JANELA):
            await do_jogador.receive_json_from()
            await do_mestre.receive_json_from()
        await do_jogador.receive_json_from()  # o aviso de ritmo

        resposta = await self.enviar(do_mestre, "o mestre segue falando")
        self.assertEqual(resposta["texto"], "o mestre segue falando")
        await do_jogador.receive_json_from()

        await do_jogador.disconnect()
        await do_mestre.disconnect()

    async def test_passada_a_janela_volta_a_poder_enviar(self):
        relogio = RelogioFalso()
        with mock.patch.object(consumers, "time", relogio):
            conexao = comunicador(self.campanha, self.jogador)
            await conexao.connect()
            for i in range(consumers.MAX_MENSAGENS_NA_JANELA):
                await self.enviar(conexao, f"mensagem {i}")
            self.assertEqual((await self.enviar(conexao, "cedo demais"))["tipo"], "erro")

            relogio.agora += consumers.JANELA_DE_ENVIO_SEGUNDOS + 1
            resposta = await self.enviar(conexao, "agora pode")
            self.assertEqual(resposta["texto"], "agora pode")
            await conexao.disconnect()

    async def test_mensagem_em_branco_nao_gasta_o_limite(self):
        conexao = comunicador(self.campanha, self.jogador)
        await conexao.connect()
        for _ in range(consumers.MAX_MENSAGENS_NA_JANELA * 2):
            await conexao.send_json_to({"texto": "   "})
        resposta = await self.enviar(conexao, "oi")
        self.assertEqual(resposta["texto"], "oi")
        await conexao.disconnect()
