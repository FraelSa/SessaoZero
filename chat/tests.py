import datetime

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from core.base_testes import MongoTestCase

from .consumers import ChatConsumer
from .models import MensagemChat


def comunicador(campanha, usuario):
    """Conexão WebSocket de `usuario` ao chat de `campanha`, já com a sessão
    que o AuthMiddlewareStack preencheria em produção."""
    conexao = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{campanha.id}/")
    conexao.scope["url_route"] = {"kwargs": {"campanha_id": str(campanha.id)}}
    conexao.scope["session"] = {"usuario_id": str(usuario.id)} if usuario else {}
    return conexao


class ChatTests(MongoTestCase):
    """Chat em tempo real: acesso e hora da mensagem no fuso de cada pessoa (RD04)."""

    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")  # Bahia, UTC-3
        self.jogador = self.criar_usuario("jogador", fuso_horario="America/Manaus")  # UTC-4
        self.estranho = self.criar_usuario("estranho")
        self.campanha = self.criar_campanha(
            self.mestre, jogadores_inscritos_emails=[self.jogador.email]
        )

    async def test_cada_participante_recebe_a_hora_no_proprio_fuso(self):
        do_mestre = comunicador(self.campanha, self.mestre)
        do_jogador = comunicador(self.campanha, self.jogador)
        self.assertTrue((await do_mestre.connect())[0])
        self.assertTrue((await do_jogador.connect())[0])

        await do_mestre.send_json_to({"texto": "Boa noite, mesa"})
        para_o_mestre = await do_mestre.receive_json_from()
        para_o_jogador = await do_jogador.receive_json_from()

        salva = await sync_to_async(lambda: MensagemChat.objects.get())()
        esperado_bahia = (salva.criado_em - datetime.timedelta(hours=3)).strftime("%H:%M")
        esperado_manaus = (salva.criado_em - datetime.timedelta(hours=4)).strftime("%H:%M")

        self.assertEqual(para_o_mestre["texto"], "Boa noite, mesa")
        self.assertEqual(para_o_mestre["criado_em"], esperado_bahia)
        self.assertEqual(para_o_jogador["criado_em"], esperado_manaus)
        self.assertNotEqual(para_o_mestre["criado_em"], para_o_jogador["criado_em"])

        await do_mestre.disconnect()
        await do_jogador.disconnect()

    async def test_quem_nao_participa_da_campanha_e_recusado(self):
        conexao = comunicador(self.campanha, self.estranho)
        self.assertFalse((await conexao.connect())[0])

    async def test_sem_login_e_recusado(self):
        conexao = comunicador(self.campanha, None)
        self.assertFalse((await conexao.connect())[0])

    async def test_mensagem_bloqueada_pela_moderacao_so_volta_para_quem_enviou(self):
        do_mestre = comunicador(self.campanha, self.mestre)
        do_jogador = comunicador(self.campanha, self.jogador)
        await do_mestre.connect()
        await do_jogador.connect()

        await do_mestre.send_json_to({"texto": "você é um idiota"})
        resposta = await do_mestre.receive_json_from()
        self.assertEqual(resposta["tipo"], "erro")
        self.assertTrue(await do_jogador.receive_nothing())
        self.assertEqual(await sync_to_async(MensagemChat.objects.count)(), 0)

        await do_mestre.disconnect()
        await do_jogador.disconnect()
