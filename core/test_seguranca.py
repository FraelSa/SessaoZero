"""RNF03 - dados e tráfego protegidos: diagnóstico fechado, avisos com prazo e HTTPS."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import Client, SimpleTestCase, override_settings

from notificacoes.models import RETENCAO_DIAS, Notificacao

from .base_testes import MongoTestCase

RAIZ = Path(settings.BASE_DIR)


@override_settings(MODERADORES_EMAILS=["mod@exemplo.com"])
class StatusDoMongoTests(MongoTestCase):
    def test_em_desenvolvimento_qualquer_um_ve(self):
        with override_settings(DEBUG=True):
            resposta = Client().get("/status/mongo/")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["conectado"])

    @override_settings(DEBUG=False)
    def test_em_producao_visitante_recebe_404(self):
        self.assertEqual(Client().get("/status/mongo/").status_code, 404)

    @override_settings(DEBUG=False)
    def test_em_producao_usuario_comum_recebe_404(self):
        self.entrar(self.criar_usuario("ana"))
        self.assertEqual(self.client.get("/status/mongo/").status_code, 404)

    @override_settings(DEBUG=False)
    def test_em_producao_moderador_ve(self):
        self.entrar(self.criar_usuario("mod"))
        resposta = self.client.get("/status/mongo/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("banco", resposta.json())

    @override_settings(DEBUG=False)
    def test_em_producao_o_erro_nao_mostra_o_endereco_do_servidor(self):
        self.entrar(self.criar_usuario("mod"))
        erro = RuntimeError("falhou em mongodb+srv://usuario:segredo@cluster0.exemplo.mongodb.net")
        with mock.patch("core.views.get_db", side_effect=erro):
            resposta = self.client.get("/status/mongo/")
        self.assertEqual(resposta.status_code, 500)
        self.assertEqual(resposta.json()["erro"], "RuntimeError")
        self.assertNotIn("segredo", resposta.content.decode())

    def test_em_desenvolvimento_o_erro_vem_completo(self):
        erro = RuntimeError("não achei o servidor")
        with override_settings(DEBUG=True), mock.patch("core.views.get_db", side_effect=erro):
            resposta = Client().get("/status/mongo/")
        self.assertEqual(resposta.json()["erro"], "não achei o servidor")


class RetencaoDosAvisosTests(MongoTestCase):
    def test_os_avisos_somem_sozinhos_do_banco_em_90_dias(self):
        indices = Notificacao._get_collection().index_information()
        ttl = [info for info in indices.values() if "expireAfterSeconds" in info]
        self.assertEqual(len(ttl), 1)
        self.assertEqual(RETENCAO_DIAS, 90)
        self.assertEqual(ttl[0]["expireAfterSeconds"], 90 * 24 * 3600)

    def test_a_contagem_de_nao_lidas_tem_indice_proprio(self):
        indices = Notificacao._get_collection().index_information()
        chaves = [tuple(campo for campo, _ in info["key"]) for info in indices.values()]
        self.assertIn(("destinatario_email", "lida"), chaves)


def configuracao_com(**ambiente):
    """Carrega o settings.py num processo à parte, com as variáveis dadas, e devolve
    o que importa para a segurança. Processo à parte porque o settings.py abre a
    conexão com o banco e decide coisas na hora em que é importado."""
    codigo = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import sessao_zero.settings as s\n"
        "campos = ['DEBUG', 'SECURE_SSL_REDIRECT', 'SECURE_REDIRECT_EXEMPT', 'SECURE_HSTS_SECONDS',\n"
        "          'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'SECURE_PROXY_SSL_HEADER']\n"
        "print(json.dumps({c: getattr(s, c, None) for c in campos}))\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
    env.update(ambiente)
    resultado = subprocess.run(
        [sys.executable, "-c", codigo, str(RAIZ)],
        capture_output=True,
        text=True,
        env=env,
        cwd=RAIZ,
        timeout=60,
    )
    if resultado.returncode != 0:
        raise AssertionError(resultado.stderr)
    return json.loads(resultado.stdout.strip().splitlines()[-1])


class ConfiguracaoDeProducaoTests(SimpleTestCase):
    PRODUCAO = {"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "chave-so-para-este-teste"}

    def test_em_producao_http_vai_para_https_e_o_navegador_passa_a_exigir_https(self):
        config = configuracao_com(**self.PRODUCAO)
        self.assertTrue(config["SECURE_SSL_REDIRECT"])
        self.assertGreaterEqual(config["SECURE_HSTS_SECONDS"], 3600)
        self.assertTrue(config["SESSION_COOKIE_SECURE"])
        self.assertTrue(config["CSRF_COOKIE_SECURE"])
        self.assertEqual(config["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_o_teste_de_saude_nao_e_redirecionado(self):
        config = configuracao_com(**self.PRODUCAO)
        self.assertEqual(config["SECURE_REDIRECT_EXEMPT"], [r"^saude/$"])

    def test_o_prazo_do_hsts_e_o_redirecionamento_podem_ser_ajustados(self):
        config = configuracao_com(
            **self.PRODUCAO, DJANGO_HSTS_SEGUNDOS="31536000", DJANGO_SSL_REDIRECT="False"
        )
        self.assertEqual(config["SECURE_HSTS_SECONDS"], 31536000)
        self.assertFalse(config["SECURE_SSL_REDIRECT"])

    def test_em_desenvolvimento_nada_disso_atrapalha_o_http_local(self):
        config = configuracao_com(DJANGO_DEBUG="True")
        self.assertFalse(config["SECURE_SSL_REDIRECT"])
        self.assertFalse(config["SECURE_HSTS_SECONDS"])
        self.assertFalse(config["SESSION_COOKIE_SECURE"])
