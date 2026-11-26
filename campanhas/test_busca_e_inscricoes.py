import datetime

from core.base_testes import MongoTestCase

from .busca import MAX_PALAVRAS, filtrar_por_palavras, palavras_da_busca
from .models import Campanha


def titulos(resposta):
    """Títulos das campanhas na página, na ordem em que aparecem."""
    return [c.titulo for c in resposta.context["campanhas"]]


class PalavrasDaBuscaTests(MongoTestCase):
    def test_tira_acento_caixa_e_repeticao(self):
        self.assertEqual(palavras_da_busca("  Ação  AÇÃO  Dragão "), ["acao", "dragao"])

    def test_vazio_e_none_nao_geram_palavras(self):
        self.assertEqual(palavras_da_busca(""), [])
        self.assertEqual(palavras_da_busca(None), [])

    def test_limita_o_numero_de_palavras(self):
        busca = " ".join(f"p{i}" for i in range(20))
        self.assertEqual(len(palavras_da_busca(busca)), MAX_PALAVRAS)


class BuscaPorPalavraChaveTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.criar_usuario("ana")
        self.bruno = self.criar_usuario("bruno")
        self.strahd = self.criar_campanha(
            self.ana,
            titulo="A Maldição de Strahd",
            sinopse="Terror gótico em Barovia.",
            sistema_rpg="D&D 5e",
        )
        self.cthulhu = self.criar_campanha(
            self.bruno,
            titulo="Sussurros em Arkham",
            sinopse="Investigação sobrenatural nos anos 1920.",
            sistema_rpg="Call of Cthulhu",
        )
        self.vampiro = self.criar_campanha(
            self.bruno,
            titulo="Noites de São Paulo",
            sinopse="Intriga entre clãs na capital paulista.",
            sistema_rpg="Vampiro: A Máscara",
        )

    def buscar(self, **params):
        return self.client.get("/campanhas/", params)

    def test_sem_busca_lista_tudo_e_nao_mostra_contagem(self):
        resposta = self.buscar()
        self.assertEqual(len(titulos(resposta)), 3)
        self.assertIsNone(resposta.context["total"])

    def test_acha_pelo_titulo(self):
        self.assertEqual(titulos(self.buscar(q="strahd")), ["A Maldição de Strahd"])

    def test_acha_pela_sinopse(self):
        self.assertEqual(titulos(self.buscar(q="barovia")), ["A Maldição de Strahd"])

    def test_acha_pelo_sistema(self):
        self.assertEqual(titulos(self.buscar(q="cthulhu")), ["Sussurros em Arkham"])

    def test_acha_pelo_nome_do_mestre(self):
        self.assertCountEqual(
            titulos(self.buscar(q="bruno")), ["Sussurros em Arkham", "Noites de São Paulo"]
        )

    def test_ignora_maiusculas(self):
        self.assertEqual(titulos(self.buscar(q="STRAHD")), ["A Maldição de Strahd"])

    def test_digitar_sem_acento_acha_texto_acentuado(self):
        self.assertEqual(titulos(self.buscar(q="maldicao")), ["A Maldição de Strahd"])
        self.assertEqual(titulos(self.buscar(q="sao paulo")), ["Noites de São Paulo"])

    def test_digitar_com_acento_acha_texto_sem_acento(self):
        self.assertEqual(titulos(self.buscar(q="gótico")), ["A Maldição de Strahd"])
        # "Investigação" está acentuado; "Investigacao" no banco não existe,
        # então confere o caminho inverso com um texto gravado sem acento.
        self.criar_campanha(self.ana, titulo="Cronicas do Norte", sinopse="Sem acentos.")
        self.assertEqual(titulos(self.buscar(q="Crônicas")), ["Cronicas do Norte"])

    def test_varias_palavras_precisam_aparecer_todas(self):
        self.assertEqual(titulos(self.buscar(q="terror strahd")), ["A Maldição de Strahd"])
        self.assertEqual(titulos(self.buscar(q="terror arkham")), [])

    def test_as_palavras_podem_estar_em_campos_diferentes(self):
        # "ana" é a mestra, "terror" está na sinopse.
        self.assertEqual(titulos(self.buscar(q="ana terror")), ["A Maldição de Strahd"])

    def test_caracteres_especiais_valem_como_texto_e_nao_como_regex(self):
        self.assertEqual(titulos(self.buscar(q=".*")), [])
        self.assertEqual(titulos(self.buscar(q="D&D")), ["A Maldição de Strahd"])
        self.assertEqual(titulos(self.buscar(q="(")), [])

    def test_combina_com_o_filtro_de_sistema(self):
        resposta = self.buscar(q="bruno", sistema="Call of Cthulhu")
        self.assertEqual(titulos(resposta), ["Sussurros em Arkham"])
        resposta = self.buscar(q="strahd", sistema="Call of Cthulhu")
        self.assertEqual(titulos(resposta), [])

    def test_mostra_quantas_foram_encontradas(self):
        resposta = self.buscar(q="bruno")
        self.assertEqual(resposta.context["total"], 2)
        self.assertContains(resposta, "2 campanhas encontradas para “bruno”")

        resposta = self.buscar(q="strahd")
        self.assertContains(resposta, "1 campanha encontrada para “strahd”")

    def test_sem_resultado_diz_e_sugere_outras_palavras(self):
        resposta = self.buscar(q="zzzz")
        self.assertContains(resposta, "Nenhuma campanha encontrada para “zzzz”")
        self.assertContains(resposta, "Tente outras palavras")

    def test_o_termo_buscado_e_escapado_na_pagina(self):
        resposta = self.buscar(q="<script>alert(1)</script>")
        self.assertNotContains(resposta, "<script>alert(1)</script>")
        self.assertContains(resposta, "&lt;script&gt;")

    def test_campo_de_busca_volta_preenchido(self):
        self.assertContains(self.buscar(q="strahd"), 'value="strahd"')

    def test_busca_so_com_espacos_equivale_a_sem_busca(self):
        self.assertEqual(len(titulos(self.buscar(q="   "))), 3)

    def test_busca_enorme_e_cortada_sem_erro(self):
        resposta = self.buscar(q="a" * 5000)
        self.assertEqual(resposta.status_code, 200)

    def test_busca_inclui_campanhas_lotadas(self):
        self.strahd.max_jogadores = 1
        self.strahd.inscrever_jogador(self.bruno.email)
        resposta = self.buscar(q="strahd")
        self.assertEqual(titulos(resposta), ["A Maldição de Strahd"])

    def test_filtrar_por_palavras_sem_palavras_devolve_o_queryset(self):
        self.assertEqual(filtrar_por_palavras(Campanha.objects, "  ").count(), 3)


class MinhasInscricoesTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.joao = self.criar_usuario("joao")
        self.maria = self.criar_usuario("maria")

    def abrir(self, usuario=None):
        if usuario:
            self.entrar(usuario)
        return self.client.get("/campanhas/inscricoes/")

    def inscrito(self, **extras):
        extras.setdefault("jogadores_inscritos_emails", [self.joao.email])
        return self.criar_campanha(self.mestre, **extras)

    def test_exige_login(self):
        resposta = self.client.get("/campanhas/inscricoes/")
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("login", resposta.url)

    def test_a_rota_nao_e_confundida_com_o_id_de_uma_campanha(self):
        resposta = self.abrir(self.joao)
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "campanhas/minhas_inscricoes.html")

    def test_sem_inscricoes_mostra_o_vazio_com_caminhos_para_achar_mesas(self):
        resposta = self.abrir(self.joao)
        self.assertEqual(resposta.context["total"], 0)
        self.assertContains(resposta, "Você ainda não está inscrito em nenhuma mesa")
        self.assertContains(resposta, 'href="/campanhas/"')
        self.assertContains(resposta, 'href="/campanhas/recomendadas/"')

    def test_lista_so_as_mesas_em_que_a_pessoa_esta_inscrita(self):
        minha = self.inscrito(titulo="Minha mesa")
        self.criar_campanha(self.mestre, titulo="Outra mesa")  # sem inscritos
        self.criar_campanha(
            self.mestre, titulo="Mesa da Maria", jogadores_inscritos_emails=[self.maria.email]
        )
        resposta = self.abrir(self.joao)
        self.assertEqual(resposta.context["total"], 1)
        self.assertContains(resposta, "Minha mesa")
        self.assertNotContains(resposta, "Outra mesa")
        self.assertNotContains(resposta, "Mesa da Maria")
        self.assertContains(resposta, f"/campanhas/{minha.id}/")

    def test_quem_so_mestra_nao_ve_a_propria_mesa_como_inscricao(self):
        self.inscrito(titulo="Mesa do mestre")
        self.assertEqual(self.abrir(self.mestre).context["total"], 0)

    def test_mostra_o_total_no_singular_e_no_plural(self):
        self.inscrito(titulo="Primeira")
        self.assertContains(self.abrir(self.joao), "Você está inscrito em 1 mesa.")
        self.inscrito(titulo="Segunda")
        self.assertContains(self.abrir(), "Você está inscrito em 2 mesas.")

    def test_agrupa_ordena_pela_proxima_sessao_e_separa_sem_data_e_realizadas(self):
        agora = datetime.datetime.utcnow().replace(microsecond=0)
        self.inscrito(titulo="Daqui a dez dias", data_sessao=agora + datetime.timedelta(days=10))
        self.inscrito(titulo="Daqui a dois dias", data_sessao=agora + datetime.timedelta(days=2))
        self.inscrito(titulo="Sem data")
        self.inscrito(titulo="Há um mês", data_sessao=agora - datetime.timedelta(days=30))
        self.inscrito(titulo="Há uma semana", data_sessao=agora - datetime.timedelta(days=7))

        resposta = self.abrir(self.joao)
        nomes = lambda chave: [c.titulo for c in resposta.context[chave]]  # noqa: E731
        self.assertEqual(nomes("proximas"), ["Daqui a dois dias", "Daqui a dez dias"])
        self.assertEqual(nomes("sem_data"), ["Sem data"])
        self.assertEqual(nomes("realizadas"), ["Há uma semana", "Há um mês"])
        for rotulo in ("Próximas sessões", "Sem data definida", "Sessões já realizadas"):
            self.assertContains(resposta, rotulo)

    def test_mesa_recorrente_antiga_fica_nas_proximas(self):
        agora = datetime.datetime.utcnow()
        self.inscrito(
            titulo="Toda semana",
            recorrencia="semanal",
            data_sessao=agora - datetime.timedelta(days=60),
        )
        resposta = self.abrir(self.joao)
        self.assertEqual([c.titulo for c in resposta.context["proximas"]], ["Toda semana"])
        self.assertEqual(list(resposta.context["realizadas"]), [])

    def test_grupos_vazios_nao_mostram_titulo(self):
        self.inscrito(titulo="Sem data")
        resposta = self.abrir(self.joao)
        self.assertContains(resposta, "Sem data definida")
        self.assertNotContains(resposta, "Próximas sessões")
        self.assertNotContains(resposta, "Sessões já realizadas")

    def test_inscrever_se_faz_a_mesa_aparecer_na_lista(self):
        campanha = self.criar_campanha(self.mestre, titulo="Entrei agora")
        self.entrar(self.joao)
        self.assertEqual(self.abrir().context["total"], 0)
        self.client.post(f"/campanhas/{campanha.id}/inscrever/")
        resposta = self.abrir()
        self.assertEqual(resposta.context["total"], 1)
        self.assertContains(resposta, "Entrei agora")

    def test_mesa_lotada_continua_na_lista_de_quem_esta_inscrito(self):
        self.inscrito(titulo="Lotada", max_jogadores=1, status="lotada")
        self.assertContains(self.abrir(self.joao), "Lotada")

    def test_link_na_navegacao_so_aparece_para_quem_entrou(self):
        anonimo = self.client.get("/campanhas/")
        self.assertNotContains(anonimo, "Minhas inscrições")
        self.entrar(self.joao)
        logado = self.client.get("/campanhas/")
        self.assertContains(logado, 'href="/campanhas/inscricoes/"')
        self.assertContains(logado, "Minhas inscrições")

    def test_pagina_marca_o_link_atual_na_navegacao(self):
        resposta = self.abrir(self.joao)
        self.assertContains(
            resposta, 'href="/campanhas/inscricoes/" aria-current="page"'
        )
