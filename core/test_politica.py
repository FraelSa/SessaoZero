"""RNF03 - a Política de Privacidade diz o que o código de fato faz.

Os prazos e limites da página vêm das mesmas constantes que o código usa; estes
testes conferem a página contra o que está configurado no banco e nos arquivos, para
ela não ficar desatualizada em silêncio."""

import re

from django.test import Client

from accounts import limite_login
from accounts.models import TentativaLogin
from moderacao.models import ConteudoBloqueado
from notificacoes.models import Notificacao

from . import politica
from .apoio_testes import RAIZ
from .base_testes import MongoTestCase


def segundos_de_expiracao(documento):
    """O prazo, em segundos, do índice TTL que o MongoDB usa para apagar o documento."""
    for indice in documento._meta["indexes"]:
        if isinstance(indice, dict) and "expireAfterSeconds" in indice:
            return indice["expireAfterSeconds"]
    raise AssertionError(f"{documento.__name__} não tem índice de expiração")


def texto_da_pagina():
    html = Client().get("/privacidade/").content.decode()
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


class PrazosDaPoliticaTests(MongoTestCase):
    def test_os_avisos_ficam_pelo_prazo_do_indice_de_expiracao(self):
        dias = segundos_de_expiracao(Notificacao) // 86400
        texto = texto_da_pagina()
        self.assertIn(f"ficam guardados por {dias} dias", texto)
        self.assertIn(f"os avisos: {dias} dias", texto)

    def test_os_textos_barrados_ficam_pelo_prazo_do_indice_de_expiracao(self):
        dias = segundos_de_expiracao(ConteudoBloqueado) // 86400
        texto = texto_da_pagina()
        self.assertIn(f"por {dias} dias, para revisão", texto)
        self.assertIn(f"pela moderação: {dias} dias", texto)

    def test_as_tentativas_de_entrada_ficam_por_1_hora(self):
        self.assertEqual(segundos_de_expiracao(TentativaLogin), 3600)
        texto = texto_da_pagina()
        self.assertIn("por até 1 hora a hora de cada senha errada", texto)
        self.assertIn("tentativas de entrada com senha errada: 1 hora", texto)

    def test_o_limite_de_tentativas_e_o_do_codigo(self):
        minutos = int(limite_login.JANELA.total_seconds() // 60)
        self.assertIn(f"{limite_login.LIMITE_DE_FALHAS} erros em {minutos} minutos", texto_da_pagina())

    def test_os_prazos_vem_das_constantes_do_codigo(self):
        prazos = politica.prazos()
        self.assertEqual(prazos["dias_avisos"], segundos_de_expiracao(Notificacao) // 86400)
        self.assertEqual(prazos["dias_moderacao"], segundos_de_expiracao(ConteudoBloqueado) // 86400)
        self.assertEqual(prazos["limite_de_falhas"], limite_login.LIMITE_DE_FALHAS)


class AfirmacoesDaPoliticaTests(MongoTestCase):
    def test_nao_diz_mais_que_usa_o_google_fonts_e_diz_que_nao_se_conecta_a_terceiros(self):
        texto = texto_da_pagina()
        self.assertNotIn("Google Fonts", texto)
        self.assertIn("não precisa se conectar ao Google", texto)

    def test_o_css_tambem_nao_busca_nada_em_outro_site(self):
        css = (RAIZ / "core" / "static" / "core" / "css" / "sessao_zero.css").read_text()
        self.assertIsNone(re.search(r"url\(\s*[\"']?(?:https?:)?//", css))
        self.assertNotIn("@import", css)

    def test_aponta_para_onde_cada_dado_e_corrigido(self):
        html = Client().get("/privacidade/").content.decode()
        for rota in ("/contas/perfil/", "/contas/preferencias/", "/contas/conta/"):
            self.assertIn(f'href="{rota}"', html)

    def test_nao_manda_mais_falar_com_a_equipe_para_trocar_nome_ou_email(self):
        self.assertNotIn("Para mudar o nome de usuário ou o e-mail", texto_da_pagina())

    def test_a_versao_mostrada_e_a_que_o_cadastro_grava(self):
        self.assertIn(politica.VERSAO, texto_da_pagina())
        self.assertRegex(politica.VERSAO, r"^\d{4}-\d{2}-\d{2}$")
