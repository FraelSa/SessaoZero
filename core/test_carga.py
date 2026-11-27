"""RNF01 / RNF05 - a ferramenta de teste de carga mede e avisa direito."""

from io import StringIO

import mongomock
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import LiveServerTestCase, SimpleTestCase
from mongoengine import connect, disconnect

from accounts.models import Usuario

from . import carga
from .base_testes import DOCUMENTOS, SENHA_PADRAO
from .carga import Medida


def medidas(caminho, tempos, status=200):
    return [Medida(caminho, tempo, status) for tempo in tempos]


class CalculosTests(SimpleTestCase):
    def test_percentil_pelo_posto_mais_proximo(self):
        valores = list(range(1, 101))  # 1 a 100
        self.assertEqual(carga.percentil(valores, 50), 50)
        self.assertEqual(carga.percentil(valores, 95), 95)
        self.assertEqual(carga.percentil(valores, 99), 99)
        self.assertEqual(carga.percentil(valores, 100), 100)

    def test_percentil_de_poucos_valores_e_de_lista_vazia(self):
        self.assertEqual(carga.percentil([3.0], 95), 3.0)
        self.assertEqual(carga.percentil([1.0, 9.0], 95), 9.0)
        self.assertEqual(carga.percentil([], 95), 0.0)

    def test_o_resumo_separa_as_paginas_e_conta_as_falhas(self):
        todas = (
            medidas("/", [0.1, 0.2, 0.3])
            + medidas("/campanhas/", [0.5, 1.5])
            + medidas("/campanhas/", [0.0], status=0)
            + medidas("/x/", [0.1], status=500)
        )
        resumo = carga.resumir(todas, duracao_s=10)
        self.assertEqual(list(resumo["paginas"]), ["/", "/campanhas/", "/x/"])
        self.assertEqual(resumo["paginas"]["/"]["requisicoes"], 3)
        self.assertEqual(resumo["paginas"]["/campanhas/"]["falhas"], 1)
        self.assertEqual(resumo["paginas"]["/x/"]["falhas"], 1)
        self.assertEqual(resumo["geral"]["requisicoes"], 7)
        self.assertEqual(resumo["geral"]["falhas"], 2)
        self.assertAlmostEqual(resumo["geral"]["por_segundo"], 0.7)

    def test_status_400_e_acima_contam_como_falha_mas_3xx_nao(self):
        resumo = carga.resumir(medidas("/a/", [0.1], 302) + medidas("/b/", [0.1], 404), 1)
        self.assertEqual(resumo["paginas"]["/a/"]["falhas"], 0)
        self.assertEqual(resumo["paginas"]["/b/"]["falhas"], 1)


class AvaliacaoTests(SimpleTestCase):
    def test_tudo_dentro_do_limite_passa(self):
        resumo = carga.resumir(medidas("/", [0.2] * 50) + medidas("/campanhas/", [1.9] * 50), 10)
        self.assertEqual(carga.avaliar(resumo), [])

    def test_pagina_com_p95_acima_de_2_segundos_e_apontada(self):
        lentas = medidas("/campanhas/", [0.3] * 90 + [2.6] * 10)
        problemas = carga.avaliar(carga.resumir(medidas("/", [0.1] * 20) + lentas, 10))
        self.assertEqual(len(problemas), 1)
        self.assertIn("/campanhas/", problemas[0])
        self.assertIn("2.60 s", problemas[0])

    def test_poucas_respostas_lentas_nao_reprovam_o_p95(self):
        quase_todas_rapidas = medidas("/", [0.2] * 97 + [5.0] * 3)
        self.assertEqual(carga.avaliar(carga.resumir(quase_todas_rapidas, 10)), [])

    def test_mais_de_1_por_cento_de_falhas_reprova(self):
        com_falhas = medidas("/", [0.1] * 95) + medidas("/", [0.1] * 5, status=503)
        problemas = carga.avaliar(carga.resumir(com_falhas, 10))
        self.assertTrue(any("5.0%" in p for p in problemas))

    def test_ate_1_por_cento_de_falhas_passa(self):
        resumo = carga.resumir(medidas("/", [0.1] * 99) + medidas("/", [0.1], status=0), 10)
        self.assertEqual(carga.avaliar(resumo), [])

    def test_sem_nenhuma_requisicao_e_problema(self):
        self.assertEqual(carga.avaliar(carga.resumir([], 10)), ["Nenhuma requisição foi concluída."])

    def test_o_relatorio_mostra_as_colunas_o_total_e_os_problemas(self):
        resumo = carga.resumir(medidas("/campanhas/", [3.0] * 10), 10)
        resultado = {
            "base": "https://exemplo.onrender.com", "usuarios": 20, "duracao_s": 10, "com_login": False,
            "logins": None, "partida_a_frio_s": 41.2, "resumo": resumo,
            "problemas": carga.avaliar(resumo),
        }
        texto = carga.formatar(resultado)
        self.assertIn("https://exemplo.onrender.com", texto)
        self.assertIn("partida a frio): 41.2 s", texto)
        self.assertIn("/campanhas/", texto)
        self.assertIn("TOTAL", texto)
        self.assertIn("PROBLEMAS:", texto)
        self.assertNotIn("Passou", texto)

    def test_o_relatorio_de_um_teste_que_passou_diz_que_passou(self):
        resumo = carga.resumir(medidas("/", [0.2] * 10), 10)
        resultado = {
            "base": "http://x", "usuarios": 5, "duracao_s": 10, "com_login": False, "logins": None,
            "partida_a_frio_s": None, "resumo": resumo, "problemas": [],
        }
        self.assertIn("Passou", carga.formatar(resultado))

    def test_avisa_que_o_computador_pode_ser_o_gargalo_com_muitos_usuarios(self):
        resumo = carga.resumir(medidas("/", [0.2] * 10), 10)
        base = {"base": "http://x", "duracao_s": 10, "com_login": False, "logins": None,
                "partida_a_frio_s": None, "resumo": resumo, "problemas": []}
        self.assertNotIn("gargalo", carga.formatar({**base, "usuarios": 500}))
        self.assertIn("gargalo", carga.formatar({**base, "usuarios": 501}))


class ComandoTests(SimpleTestCase):
    def rodar(self, *args):
        saida = StringIO()
        call_command("teste_de_carga", *args, stdout=saida)
        return saida.getvalue()

    def test_recusa_endereco_sem_http(self):
        with self.assertRaisesMessage(CommandError, "http://"):
            self.rodar("exemplo.com")

    def test_recusa_numeros_invalidos(self):
        with self.assertRaises(CommandError):
            self.rodar("http://localhost", "--usuarios", "0")
        with self.assertRaises(CommandError):
            self.rodar("http://localhost", "--duracao", "0")

    def test_entrar_precisa_de_email_e_senha(self):
        for valor in ("so-o-email", ":senha", "email:"):
            with self.assertRaisesMessage(CommandError, "--entrar EMAIL:SENHA"):
                self.rodar("http://localhost", "--entrar", valor)


class TesteContraUmServidorDeVerdadeTests(LiveServerTestCase):
    """Sobe o site de verdade (com o MongoDB simulado) e roda o teste contra ele."""

    @classmethod
    def setUpClass(cls):
        disconnect()
        connect("sessao_zero_teste", host="mongodb://localhost", mongo_client_class=mongomock.MongoClient)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        disconnect()

    def setUp(self):
        for documento in DOCUMENTOS:
            documento.drop_collection()

    def test_mede_as_paginas_publicas_sem_erros(self):
        resultado = carga.executar(
            self.live_server_url, usuarios=3, duracao_s=2, pausa_s=0.05, subida_s=0.2
        )
        resumo = resultado["resumo"]
        self.assertGreater(resumo["geral"]["requisicoes"], 6)
        self.assertEqual(resumo["geral"]["falhas"], 0)
        self.assertEqual(set(resumo["paginas"]), set(carga.PAGINAS_PUBLICAS))
        self.assertIsNotNone(resultado["partida_a_frio_s"])
        self.assertEqual(resultado["problemas"], [])
        self.assertIsNone(resultado["logins"])

    def test_com_login_visita_tambem_as_paginas_de_quem_esta_logado(self):
        usuario = Usuario(username="ana", email="ana@exemplo.com")
        usuario.set_senha(SENHA_PADRAO)
        usuario.save()
        resultado = carga.executar(
            self.live_server_url, usuarios=2, duracao_s=4, pausa_s=0.05, subida_s=0.2,
            login=("ana@exemplo.com", SENHA_PADRAO), aquecer_antes=False,
        )
        self.assertEqual(resultado["logins"], {"ok": 2, "falhas": 0})
        paginas = set(resultado["resumo"]["paginas"])
        self.assertTrue(paginas & set(carga.PAGINAS_DE_USUARIO), "nenhuma página de quem está logado")
        self.assertEqual(resultado["resumo"]["geral"]["falhas"], 0)
        self.assertEqual(resultado["problemas"], [])

    def test_senha_errada_aparece_como_problema(self):
        usuario = Usuario(username="ana", email="ana@exemplo.com")
        usuario.set_senha(SENHA_PADRAO)
        usuario.save()
        resultado = carga.executar(
            self.live_server_url, usuarios=1, duracao_s=1, pausa_s=0.05, subida_s=0,
            login=("ana@exemplo.com", "senha-errada-1"), aquecer_antes=False,
        )
        self.assertEqual(resultado["logins"], {"ok": 0, "falhas": 1})
        self.assertTrue(any("Nenhum login funcionou" in p for p in resultado["problemas"]))

    def test_servidor_que_nao_existe_vira_falhas_e_nao_excecao(self):
        resultado = carga.executar(
            "http://127.0.0.1:9", usuarios=2, duracao_s=1, pausa_s=0.05, subida_s=0, aquecer_antes=False
        )
        geral = resultado["resumo"]["geral"]
        self.assertGreater(geral["requisicoes"], 0)
        self.assertEqual(geral["falhas"], geral["requisicoes"])
        self.assertTrue(resultado["problemas"])

    def test_o_comando_imprime_o_relatorio(self):
        saida = StringIO()
        call_command(
            "teste_de_carga", self.live_server_url, "--usuarios", "2", "--duracao", "2",
            "--pausa", "0.05", stdout=saida,
        )
        texto = saida.getvalue()
        self.assertIn("TOTAL", texto)
        self.assertIn("Passou", texto)
