"""RNF05 / RNF06 - o site fica de pé, avisa quando algo falha e escala além de um processo."""

import re
from unittest import mock

from django.template.loader import render_to_string
from django.test import Client, SimpleTestCase
from django.urls import resolve
from pymongo.errors import AutoReconnect, ServerSelectionTimeoutError

from .apoio_testes import RAIZ, ler_configuracao
from .base_testes import MongoTestCase


class SaudeTests(MongoTestCase):
    def test_o_site_de_pe_responde_ok_sem_login_e_sem_cache(self):
        resposta = Client().get("/saude/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"estado": "ok"})
        self.assertEqual(resposta.headers["Cache-Control"], "no-store")

    def test_a_saude_simples_nao_depende_do_banco(self):
        """O Render reinicia o serviço quando este endereço falha: um banco fora do ar
        não pode derrubar a resposta, senão o site seria reiniciado à toa."""
        with mock.patch("core.views.get_db", side_effect=ServerSelectionTimeoutError("fora")):
            self.assertEqual(Client().get("/saude/").status_code, 200)

    def test_aceita_head_para_os_monitores(self):
        self.assertEqual(Client().head("/saude/").status_code, 200)
        self.assertEqual(Client().head("/saude/banco/").status_code, 200)

    def test_nao_aceita_escrita(self):
        self.assertEqual(Client().post("/saude/").status_code, 405)
        self.assertEqual(Client().post("/saude/banco/").status_code, 405)

    def test_nao_cria_sessao_nem_cookie(self):
        resposta = Client().get("/saude/banco/")
        self.assertEqual(len(resposta.cookies), 0)

    def test_com_o_banco_no_ar_a_saude_do_banco_e_ok(self):
        resposta = Client().get("/saude/banco/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"estado": "ok", "banco": "ok"})

    def test_com_o_banco_fora_do_ar_a_saude_do_banco_e_503_sem_detalhes_do_erro(self):
        erro = ServerSelectionTimeoutError("cluster0-shard-00-00.exemplo.mongodb.net:27017 recusou")
        with mock.patch("core.views.get_db", side_effect=erro), self.assertLogs("core.views", "WARNING"):
            resposta = Client().get("/saude/banco/")
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json(), {"estado": "fora do ar", "banco": "indisponivel"})
        self.assertEqual(resposta.headers["Retry-After"], "30")
        self.assertNotIn("mongodb.net", resposta.content.decode())

    def test_o_ping_vai_mesmo_ao_banco(self):
        comando = mock.Mock()
        with mock.patch("core.views.get_db", return_value=mock.Mock(command=comando)):
            Client().get("/saude/banco/")
        comando.assert_called_once_with("ping")


class PaginasDeErroTests(MongoTestCase):
    """Quando o MongoDB não responde, a pessoa vê um aviso claro (503), e não uma
    tela de erro genérica; e os avisos não dependem do banco para aparecer."""

    def setUp(self):
        super().setUp()
        self.cliente = Client(raise_request_exception=False)

    def test_banco_fora_do_ar_vira_503_com_pedido_para_tentar_de_novo(self):
        erro = ServerSelectionTimeoutError("sem servidor")
        with mock.patch("campanhas.views.Campanha.objects", new=mock.Mock(exclude=mock.Mock(side_effect=erro))):
            with self.assertLogs("django.request", "ERROR"):
                resposta = self.cliente.get("/campanhas/")
        self.assertEqual(resposta.status_code, 503)
        self.assertContains(resposta, "instabilidade", status_code=503)
        self.assertEqual(resposta.headers["Retry-After"], "30")
        self.assertNotIn("sem servidor", resposta.content.decode())

    def test_o_503_tambem_vale_quando_o_erro_vem_embrulhado_em_outro(self):
        def falhar(*args, **kwargs):
            try:
                raise AutoReconnect("conexão perdida")
            except AutoReconnect as original:
                raise RuntimeError("não deu") from original

        with mock.patch("campanhas.views.Campanha.objects", new=mock.Mock(exclude=falhar)):
            with self.assertLogs("django.request", "ERROR"):
                resposta = self.cliente.get("/campanhas/")
        self.assertEqual(resposta.status_code, 503)

    def test_outro_erro_continua_sendo_500(self):
        erro = ValueError("bug no código")
        with mock.patch("campanhas.views.Campanha.objects", new=mock.Mock(exclude=mock.Mock(side_effect=erro))):
            with self.assertLogs("django.request", "ERROR"):
                resposta = self.cliente.get("/campanhas/")
        self.assertEqual(resposta.status_code, 500)
        self.assertContains(resposta, "Algo deu errado", status_code=500)
        self.assertNotIn("bug no código", resposta.content.decode())
        self.assertNotIn("Retry-After", resposta.headers)

    def test_as_paginas_de_erro_nao_usam_o_menu_nem_o_banco(self):
        for modelo in ("500.html", "503.html"):
            html = render_to_string(modelo)
            self.assertNotIn("{%", html)
            self.assertIn("<html", html)
            self.assertNotIn("href=\"https://", html)  # nada de recursos externos

    def test_visitante_sem_login_continua_vendo_a_pagina_inicial_com_o_banco_fora(self):
        erro = ServerSelectionTimeoutError("sem servidor")
        with mock.patch("core.views.Campanha.objects", new=mock.Mock(side_effect=erro)):
            self.assertEqual(self.cliente.get("/").status_code, 200)


class CanaisDoChatTests(SimpleTestCase):
    def camada(self, **ambiente):
        return ler_configuracao(
            "from channels.layers import get_channel_layer\n"
            "import django\n"
            "django.setup()\n"
            "camada = get_channel_layer()\n"
            "print(json.dumps({'backend': s.CHANNEL_LAYERS['default']['BACKEND'],\n"
            "                  'classe': type(camada).__name__,\n"
            "                  'config': s.CHANNEL_LAYERS['default'].get('CONFIG')}))\n",
            DJANGO_SETTINGS_MODULE="sessao_zero.settings",
            **ambiente,
        )

    def test_sem_redis_o_chat_usa_a_memoria_do_processo(self):
        camada = self.camada()
        self.assertEqual(camada["backend"], "channels.layers.InMemoryChannelLayer")
        self.assertEqual(camada["classe"], "InMemoryChannelLayer")

    def test_com_redis_url_o_chat_passa_a_usar_o_redis(self):
        camada = self.camada(REDIS_URL="redis://localhost:6379")
        self.assertEqual(camada["backend"], "channels_redis.core.RedisChannelLayer")
        self.assertEqual(camada["classe"], "RedisChannelLayer")
        self.assertEqual(camada["config"]["hosts"], ["redis://localhost:6379"])

    def test_com_redis_mensagens_paradas_nao_enchem_a_memoria(self):
        config = self.camada(REDIS_URL="redis://localhost:6379")["config"]
        self.assertEqual(config["expiry"], 10)
        self.assertEqual(config["capacity"], 200)


class RenderTests(SimpleTestCase):
    def test_o_render_confere_a_saude_simples_e_nao_a_que_depende_do_banco(self):
        """Se o Render consultasse /saude/banco/, uma queda do MongoDB reiniciaria o
        site em loop, sem consertar nada."""
        texto = (RAIZ / "render.yaml").read_text()
        achado = re.search(r"^\s+healthCheckPath:\s*(\S+)\s*$", texto, re.MULTILINE)
        self.assertIsNotNone(achado, "render.yaml sem healthCheckPath")
        self.assertEqual(resolve(achado.group(1)).url_name, "saude")

    def test_as_variaveis_novas_estao_no_blueprint(self):
        texto = (RAIZ / "render.yaml").read_text()
        self.assertRegex(texto, r"- key: MODERADORES_EMAILS\n\s+sync: false")
