"""RNF01 - carregamento rápido: fontes e estilos do próprio site, com cache longo, e
tempos limite que impedem uma página de ficar pendurada esperando o banco."""

import re
import shutil
import tempfile

from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management import call_command
from django.test import Client, SimpleTestCase, override_settings

from .apoio_testes import RAIZ, ler_configuracao
from .base_testes import MongoTestCase

PASTA_DAS_FONTES = RAIZ / "core" / "static" / "core" / "fonts"
FONTES = (
    "public-sans-latin-400-normal.woff2",
    "public-sans-latin-600-normal.woff2",
    "public-sans-latin-700-normal.woff2",
    "young-serif-latin-400-normal.woff2",
)
PAGINAS_PUBLICAS = ("/", "/campanhas/", "/contas/login/", "/contas/cadastro/", "/privacidade/")


class FontesDoProprioSiteTests(MongoTestCase):
    def test_os_arquivos_das_fontes_existem_e_sao_woff2(self):
        for nome in FONTES:
            conteudo = (PASTA_DAS_FONTES / nome).read_bytes()
            self.assertEqual(conteudo[:4], b"wOF2", nome)

    def test_as_licencas_das_fontes_acompanham_os_arquivos(self):
        for nome in ("LICENSE-public-sans.txt", "LICENSE-young-serif.txt"):
            self.assertIn("SIL OPEN FONT LICENSE", (PASTA_DAS_FONTES / nome).read_text())

    def test_o_css_declara_as_quatro_fontes_com_troca_imediata(self):
        css = (RAIZ / "core" / "static" / "core" / "css" / "sessao_zero.css").read_text()
        declaradas = re.findall(r'src: url\("\.\./fonts/([^"]+)"\)', css)
        self.assertCountEqual(declaradas, FONTES)
        self.assertEqual(css.count("font-display: swap;"), 4)

    def test_nenhuma_pagina_publica_pede_nada_a_outro_site(self):
        externos = re.compile(r'<(?:link|script|img|iframe)[^>]+(?:src|href)="https?://', re.I)
        for caminho in PAGINAS_PUBLICAS:
            html = Client().get(caminho).content.decode()
            self.assertIsNone(externos.search(html), f"{caminho} carrega recurso de outro site")
            self.assertNotIn("googleapis", html)
            self.assertNotIn("gstatic", html)

    def test_as_fontes_do_texto_e_do_titulo_comecam_a_baixar_antes_do_css(self):
        html = Client().get("/").content.decode()
        self.assertEqual(len(re.findall(r'<link rel="preload"[^>]+as="font"', html)), 2)
        self.assertLess(html.index('rel="preload"'), html.index('rel="stylesheet"'))


class EstaticosEmProducaoTests(MongoTestCase):
    """O que o Render faz no build (collectstatic) e o que o navegador recebe."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pasta = tempfile.mkdtemp(prefix="estaticos-")
        with override_settings(STATIC_ROOT=cls.pasta):
            call_command("collectstatic", interactive=False, verbosity=0)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        configuracao = override_settings(STATIC_ROOT=self.pasta, DEBUG=False)
        configuracao.enable()
        self.addCleanup(configuracao.disable)

    def endereco_do_css(self):
        html = Client().get("/").content.decode()
        achado = re.search(r'href="(/static/core/css/sessao_zero\.[0-9a-f]{12}\.css)\?v=', html)
        self.assertIsNotNone(achado, "o CSS não saiu com o resumo no nome")
        return achado.group(1)

    def test_o_css_tem_o_resumo_no_nome_e_sai_com_cache_de_um_ano(self):
        resposta = Client().get(self.endereco_do_css())
        self.assertEqual(resposta.status_code, 200)
        cache = resposta.headers["Cache-Control"]
        self.assertIn("max-age=31536000", cache)
        self.assertIn("immutable", cache)

    def test_o_css_aponta_para_as_fontes_com_o_resumo_e_elas_tambem_tem_cache_longo(self):
        css = b"".join(Client().get(self.endereco_do_css()).streaming_content).decode()
        enderecos = re.findall(r'url\("\.\./fonts/([^"]+)"\)', css)
        self.assertEqual(len(enderecos), 4)
        for nome in enderecos:
            self.assertRegex(nome, r"\.[0-9a-f]{12}\.woff2$")
            resposta = Client().get(f"/static/core/fonts/{nome}")
            self.assertEqual(resposta.status_code, 200, nome)
            self.assertIn("immutable", resposta.headers["Cache-Control"])

    def test_o_preload_das_fontes_usa_o_nome_com_resumo(self):
        html = Client().get("/").content.decode()
        for href in re.findall(r'<link rel="preload" href="([^"]+)"', html):
            self.assertRegex(href, r"\.[0-9a-f]{12}\.woff2$")
            self.assertEqual(Client().get(href).status_code, 200)

    def test_o_css_e_entregue_comprimido_a_quem_aceita(self):
        resposta = Client().get(self.endereco_do_css(), headers={"Accept-Encoding": "gzip"})
        self.assertEqual(resposta.headers.get("Content-Encoding"), "gzip")

    def test_o_nome_antigo_sem_resumo_continua_funcionando(self):
        """Páginas já abertas (ou em cache) que ainda apontam para o nome simples."""
        self.assertEqual(Client().get("/static/core/css/sessao_zero.css").status_code, 200)


class EstaticosSemBuildTests(SimpleTestCase):
    def test_sem_collectstatic_os_enderecos_ficam_como_estao_em_vez_de_dar_erro(self):
        vazia = tempfile.mkdtemp(prefix="vazia-")
        self.addCleanup(shutil.rmtree, vazia, ignore_errors=True)
        with override_settings(STATIC_ROOT=vazia, DEBUG=False):
            self.assertEqual(
                staticfiles_storage.url("core/css/sessao_zero.css"), "/static/core/css/sessao_zero.css"
            )


def configuracao_com(**ambiente):
    """O que importa para o desempenho no settings.py, lido como o servidor o lê."""
    return ler_configuracao(
        "from mongoengine.connection import get_connection\n"
        "o = get_connection().options\n"
        "print(json.dumps({\n"
        "    'armazenamento': s.STORAGES['staticfiles']['BACKEND'],\n"
        "    'selecao_s': o.server_selection_timeout,\n"
        "    'conexao_s': o.pool_options.connect_timeout,\n"
        "    'resposta_s': o.pool_options.socket_timeout,\n"
        "    'conexoes_max': o.pool_options.max_pool_size,\n"
        "}))\n",
        **ambiente,
    )


class ConfiguracaoDeDesempenhoTests(SimpleTestCase):
    def test_o_banco_que_nao_responde_nao_prende_a_pagina_por_30_segundos(self):
        config = configuracao_com()
        self.assertEqual(config["selecao_s"], 5)
        self.assertEqual(config["conexao_s"], 5)
        self.assertEqual(config["resposta_s"], 20)
        self.assertEqual(config["conexoes_max"], 50)

    def test_os_limites_podem_ser_ajustados_pelo_ambiente(self):
        config = configuracao_com(
            MONGO_TEMPO_SELECAO_MS="2000", MONGO_CONEXOES_MAX="80", MONGO_TEMPO_RESPOSTA_MS="30000"
        )
        self.assertEqual(config["selecao_s"], 2)
        self.assertEqual(config["conexoes_max"], 80)
        self.assertEqual(config["resposta_s"], 30)

    def test_os_estaticos_usam_nomes_com_resumo(self):
        self.assertEqual(
            configuracao_com()["armazenamento"], "core.armazenamento.ArmazenamentoDeEstaticos"
        )
