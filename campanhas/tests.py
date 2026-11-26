import datetime

from django.core.management import call_command
from django.test import Client

from core.base_testes import MongoTestCase
from core.horario import proxima_ocorrencia

from .models import Campanha
from .recomendacoes import recomendar_campanhas


def dados_do_formulario(**mudancas):
    """Campos mínimos válidos do CampanhaForm."""
    dados = {
        "titulo": "A Maldição de Strahd",
        "sistema_rpg": "D&D 5e",
        "sinopse": "Terror gótico para iniciantes.",
        "classificacao": "14",
        "max_jogadores": "3",
        "recorrencia": "unica",
        "data_sessao": "",
    }
    dados.update(mudancas)
    return dados


class StatusEVagasTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.jogador1 = self.criar_usuario("jogador1")
        self.jogador2 = self.criar_usuario("jogador2")

    def editar(self, campanha, **mudancas):
        self.entrar(self.mestre)
        return self.client.post(
            f"/campanhas/{campanha.id}/editar/", dados_do_formulario(**mudancas)
        )

    def test_ultima_inscricao_lota_a_mesa(self):
        campanha = self.criar_campanha(self.mestre, max_jogadores=1)
        campanha.inscrever_jogador(self.jogador1.email)
        campanha.reload()
        self.assertEqual(campanha.status, "lotada")

    def test_reduzir_vagas_ate_o_numero_de_inscritos_lota_a_mesa(self):
        campanha = self.criar_campanha(
            self.mestre,
            max_jogadores=3,
            jogadores_inscritos_emails=[self.jogador1.email, self.jogador2.email],
        )
        resposta = self.editar(campanha, max_jogadores="2")
        self.assertEqual(resposta.status_code, 302)
        campanha.reload()
        self.assertEqual(campanha.max_jogadores, 2)
        self.assertEqual(campanha.status, "lotada")  # antes ficava "aberta" com 0 vagas

    def test_reduzir_vagas_abaixo_dos_inscritos_e_recusado(self):
        campanha = self.criar_campanha(
            self.mestre,
            max_jogadores=3,
            jogadores_inscritos_emails=[self.jogador1.email, self.jogador2.email],
        )
        resposta = self.editar(campanha, max_jogadores="1")
        self.assertEqual(resposta.status_code, 200)  # volta ao formulário, com erro
        self.assertContains(resposta, "o mínimo de vagas é 2")
        campanha.reload()
        self.assertEqual(campanha.max_jogadores, 3)
        self.assertEqual(campanha.status, "aberta")

    def test_aumentar_vagas_reabre_a_mesa_lotada(self):
        campanha = self.criar_campanha(
            self.mestre,
            max_jogadores=2,
            status="lotada",
            jogadores_inscritos_emails=[self.jogador1.email, self.jogador2.email],
        )
        self.editar(campanha, max_jogadores="4")
        campanha.reload()
        self.assertEqual(campanha.status, "aberta")
        self.assertEqual(campanha.vagas_livres, 2)

    def test_campanha_encerrada_continua_encerrada(self):
        campanha = self.criar_campanha(self.mestre, status="encerrada")
        campanha.sincronizar_status()
        self.assertEqual(campanha.status, "encerrada")

    def test_recomendacao_ignora_mesa_sem_vaga_mesmo_com_status_antigo(self):
        # Dado de versão antiga: "aberta", 1 vaga e 2 inscritos.
        self.criar_campanha(
            self.mestre,
            titulo="Mesa cheia",
            max_jogadores=1,
            status="aberta",
            jogadores_inscritos_emails=["a@x.com", "b@x.com"],
        )
        self.criar_campanha(self.mestre, titulo="Mesa com vaga")
        usuario = self.criar_usuario("quem", preferencias={"estilos_favoritos": ["Terror"]})
        titulos = [c.titulo for c in recomendar_campanhas(usuario)]
        self.assertEqual(titulos, ["Mesa com vaga"])

    def test_comando_corrige_status_antigo(self):
        cheia = self.criar_campanha(
            self.mestre,
            titulo="Cheia",
            max_jogadores=1,
            status="aberta",
            jogadores_inscritos_emails=["a@x.com"],
        )
        folga = self.criar_campanha(self.mestre, titulo="Com folga", status="lotada")
        call_command("sincronizar_status_mesas", verbosity=0)
        cheia.reload()
        folga.reload()
        self.assertEqual(cheia.status, "lotada")
        self.assertEqual(folga.status, "aberta")


class DataDaSessaoTests(MongoTestCase):
    """Correção da data (gravada em UTC, exibida no fuso de cada pessoa) e RD04."""

    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")  # fuso padrão: America/Bahia
        self.jogador = self.criar_usuario("jogador")
        self.entrar(self.mestre)

    def criar_com_data(self, data="2026-10-29T21:00", **extras):
        resposta = self.client.post("/campanhas/nova/", dados_do_formulario(data_sessao=data, **extras))
        self.assertEqual(resposta.status_code, 302, resposta.content.decode()[:500])
        return Campanha.objects.first()

    def test_horario_digitado_vale_no_fuso_do_mestre_e_e_gravado_em_utc(self):
        campanha = self.criar_com_data()
        self.assertEqual(campanha.data_sessao, datetime.datetime(2026, 10, 30, 0, 0))
        self.assertEqual(campanha.fuso_mestre, "America/Bahia")

    def test_mestre_em_outro_fuso(self):
        manaus = self.criar_usuario("manauara", fuso_horario="America/Manaus")
        self.entrar(manaus)
        campanha = self.criar_com_data("2026-10-29T20:00")
        # 20:00 em Manaus (UTC-4) é o mesmo instante que 21:00 em Salvador.
        self.assertEqual(campanha.data_sessao, datetime.datetime(2026, 10, 30, 0, 0))
        self.assertEqual(campanha.fuso_mestre, "America/Manaus")

    def test_detalhe_mostra_o_horario_no_fuso_de_quem_ve(self):
        campanha = self.criar_com_data()
        url = f"/campanhas/{campanha.id}/"

        visitante = Client().get(url)  # sem login: fuso padrão (Bahia)
        self.assertContains(visitante, "29/10/2026, 21:00")

        manauara = self.criar_usuario("manauara", fuso_horario="America/Manaus")
        self.entrar(manauara)
        pagina = self.client.get(url)
        self.assertContains(pagina, "29/10/2026, 20:00")
        self.assertContains(pagina, "UTC-04:00")
        self.assertContains(pagina, "O mestre marcou 21:00 em Salvador, Bahia")

    def test_fuso_com_mesmo_deslocamento_nao_mostra_nota_do_mestre(self):
        campanha = self.criar_com_data()
        paulista = self.criar_usuario("paulista", fuso_horario="America/Sao_Paulo")
        self.entrar(paulista)
        pagina = self.client.get(f"/campanhas/{campanha.id}/")
        self.assertContains(pagina, "29/10/2026, 21:00")
        self.assertNotContains(pagina, "O mestre marcou")

    def test_formulario_de_edicao_vem_preenchido_com_a_data_digitada(self):
        campanha = self.criar_com_data()
        pagina = self.client.get(f"/campanhas/{campanha.id}/editar/")
        # Antes: value="30/10/2026 00:00:00", formato que o navegador descarta.
        self.assertContains(pagina, 'value="2026-10-29T21:00"')

    def test_editar_sem_mexer_na_data_nao_avisa_nova_data(self):
        campanha = self.criar_com_data()
        campanha.jogadores_inscritos_emails = [self.jogador.email]
        campanha.save()
        self.client.post(
            f"/campanhas/{campanha.id}/editar/",
            dados_do_formulario(titulo="Novo título", data_sessao="2026-10-29T21:00"),
        )
        campanha.reload()
        self.assertEqual(campanha.data_sessao, datetime.datetime(2026, 10, 30, 0, 0))
        avisos = self.textos_das_notificacoes(self.jogador)
        self.assertEqual(len(avisos), 1)
        self.assertIn("foi atualizada pelo mestre", avisos[0])

    def test_mudar_a_data_avisa_com_horario_e_fuso(self):
        campanha = self.criar_com_data()
        campanha.jogadores_inscritos_emails = [self.jogador.email]
        campanha.save()
        self.client.post(
            f"/campanhas/{campanha.id}/editar/",
            dados_do_formulario(data_sessao="2026-11-05T19:30"),
        )
        avisos = self.textos_das_notificacoes(self.jogador)
        self.assertEqual(len(avisos), 1)
        self.assertIn("nova data de sessão: 05/11/2026 19:30 (Salvador, Bahia)", avisos[0])

    def test_remover_a_data_avisa_que_foi_removida(self):
        campanha = self.criar_com_data()
        campanha.jogadores_inscritos_emails = [self.jogador.email]
        campanha.save()
        self.client.post(f"/campanhas/{campanha.id}/editar/", dados_do_formulario(data_sessao=""))
        campanha.reload()
        self.assertIsNone(campanha.data_sessao)
        self.assertIn("foi removida", self.textos_das_notificacoes(self.jogador)[0])

    def test_campanha_sem_data_mostra_a_definir(self):
        campanha = self.criar_com_data(data="")
        pagina = self.client.get(f"/campanhas/{campanha.id}/")
        self.assertContains(pagina, "A definir")

    def test_campanha_antiga_sem_os_campos_novos_continua_abrindo(self):
        # Documento como as versões anteriores gravavam: sem classificação,
        # recorrência nem fuso, e com a data em UTC.
        Campanha._get_collection().insert_one(
            {
                "titulo": "Antiga",
                "sinopse": "s",
                "sistema_rpg": "D&D 5e",
                "mestre_email": self.mestre.email,
                "mestre_username": "mestre",
                "max_jogadores": 3,
                "jogadores_inscritos_emails": [],
                "status": "aberta",
                "data_sessao": datetime.datetime(2026, 10, 30, 0, 0),
                "comentarios": [],
            }
        )
        campanha = Campanha.objects.first()
        pagina = self.client.get(f"/campanhas/{campanha.id}/")
        self.assertContains(pagina, "29/10/2026, 21:00")
        self.assertContains(pagina, "Classificação não informada")


class ProximaOcorrenciaTests(MongoTestCase):
    """RD04 - recorrência: a próxima sessão é calculada a partir da data gravada."""

    def test_sessao_unica_devolve_a_propria_data_mesmo_no_passado(self):
        inicio = datetime.datetime(2026, 1, 5, 12, 0)
        agora = datetime.datetime(2026, 6, 1)
        self.assertEqual(proxima_ocorrencia(inicio, "unica", "America/Bahia", agora), inicio)

    def test_data_ainda_no_futuro_e_a_propria_data(self):
        inicio = datetime.datetime(2026, 7, 5, 12, 0)
        agora = datetime.datetime(2026, 6, 1)
        self.assertEqual(proxima_ocorrencia(inicio, "semanal", "America/Bahia", agora), inicio)

    def test_sem_data_nao_ha_proxima(self):
        self.assertIsNone(proxima_ocorrencia(None, "semanal", "America/Bahia"))

    def test_semanal(self):
        inicio = datetime.datetime(2026, 1, 5, 12, 0)
        agora = datetime.datetime(2026, 1, 20, 8, 0)
        esperado = datetime.datetime(2026, 1, 26, 12, 0)
        self.assertEqual(proxima_ocorrencia(inicio, "semanal", "America/Bahia", agora), esperado)

    def test_quinzenal(self):
        inicio = datetime.datetime(2026, 1, 5, 12, 0)
        agora = datetime.datetime(2026, 1, 20, 8, 0)  # 19/01 já passou
        esperado = datetime.datetime(2026, 2, 2, 12, 0)
        self.assertEqual(proxima_ocorrencia(inicio, "quinzenal", "America/Bahia", agora), esperado)

    def test_sessao_exatamente_agora_conta_como_a_proxima(self):
        inicio = datetime.datetime(2026, 1, 5, 12, 0)
        agora = datetime.datetime(2026, 1, 12, 12, 0)
        self.assertEqual(proxima_ocorrencia(inicio, "semanal", "America/Bahia", agora), agora)

    def test_mensal_respeita_o_ultimo_dia_do_mes(self):
        # 31/01 às 12:00 em Brasília (15:00 UTC), todo mês.
        inicio = datetime.datetime(2026, 1, 31, 15, 0)
        fuso = "America/Sao_Paulo"
        self.assertEqual(
            proxima_ocorrencia(inicio, "mensal", fuso, datetime.datetime(2026, 2, 10)),
            datetime.datetime(2026, 2, 28, 15, 0),
        )
        self.assertEqual(
            proxima_ocorrencia(inicio, "mensal", fuso, datetime.datetime(2026, 3, 1)),
            datetime.datetime(2026, 3, 31, 15, 0),
        )

    def test_horario_de_verao_nao_desloca_o_horario_de_relogio_do_mestre(self):
        # 01/03/2026 às 20:00 em Nova York (EST, UTC-5) = 02/03 01:00 UTC.
        # O horário de verão começa em 08/03. Toda semana às 20:00 locais:
        # depois da mudança, 20:00 EDT (UTC-4) = 00:00 UTC, e não 01:00.
        inicio = datetime.datetime(2026, 3, 2, 1, 0)
        agora = datetime.datetime(2026, 3, 10)
        esperado = datetime.datetime(2026, 3, 16, 0, 0)
        self.assertEqual(proxima_ocorrencia(inicio, "semanal", "America/New_York", agora), esperado)

    def test_sessao_antiga_de_anos_atras_cai_no_futuro(self):
        inicio = datetime.datetime(2020, 1, 6, 12, 0)
        for recorrencia in ("semanal", "quinzenal", "mensal"):
            proxima = proxima_ocorrencia(inicio, recorrencia, "America/Bahia")
            self.assertGreaterEqual(proxima, datetime.datetime.utcnow(), recorrencia)
            self.assertLess(proxima - datetime.datetime.utcnow(), datetime.timedelta(days=32), recorrencia)


class RecorrenciaNasTelasTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.entrar(self.mestre)

    def test_recorrente_exige_data(self):
        resposta = self.client.post(
            "/campanhas/nova/", dados_do_formulario(recorrencia="semanal", data_sessao="")
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "para calcular a recorrência")
        self.assertEqual(Campanha.objects.count(), 0)

    def test_campanha_semanal_antiga_mostra_a_proxima_data_e_a_frequencia(self):
        campanha = self.criar_campanha(
            self.mestre,
            data_sessao=datetime.datetime(2020, 1, 6, 12, 0),
            recorrencia="semanal",
        )
        proxima = campanha.proxima_sessao
        self.assertGreater(proxima, datetime.datetime.utcnow())
        pagina = self.client.get(f"/campanhas/{campanha.id}/")
        self.assertContains(pagina, "Toda semana")
        self.assertNotContains(pagina, "06/01/2020")
        lista = self.client.get("/campanhas/")
        self.assertContains(lista, "Toda semana")

    def test_mudar_so_a_recorrencia_avisa_os_inscritos(self):
        jogador = self.criar_usuario("jogador")
        campanha = self.criar_campanha(
            self.mestre,
            data_sessao=datetime.datetime(2026, 12, 1, 0, 0),
            jogadores_inscritos_emails=[jogador.email],
        )
        self.client.post(
            f"/campanhas/{campanha.id}/editar/",
            dados_do_formulario(recorrencia="semanal", data_sessao="2026-11-30T21:00"),
        )
        campanha.reload()
        self.assertEqual(campanha.recorrencia, "semanal")
        self.assertIn("foi atualizada pelo mestre", self.textos_das_notificacoes(jogador)[0])


class ClassificacaoIndicativaTests(MongoTestCase):
    """RD03 - o mestre define a classificação indicativa de cada mesa."""

    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.entrar(self.mestre)

    def test_classificacao_e_obrigatoria(self):
        resposta = self.client.post("/campanhas/nova/", dados_do_formulario(classificacao=""))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Este campo é obrigatório")
        self.assertEqual(Campanha.objects.count(), 0)

    def test_classificacao_invalida_e_recusada(self):
        resposta = self.client.post("/campanhas/nova/", dados_do_formulario(classificacao="99"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Campanha.objects.count(), 0)

    def test_criar_com_classificacao_e_temas_e_ver_nas_telas(self):
        dados = dados_do_formulario(classificacao="16")
        dados["temas_sensiveis"] = ["terror", "violencia"]
        resposta = self.client.post("/campanhas/nova/", dados)
        self.assertEqual(resposta.status_code, 302)
        campanha = Campanha.objects.first()
        self.assertEqual(campanha.classificacao, "16")
        self.assertEqual(sorted(campanha.temas_sensiveis), ["terror", "violencia"])

        detalhe = self.client.get(f"/campanhas/{campanha.id}/")
        self.assertContains(detalhe, "16 anos")
        self.assertContains(detalhe, "Terror")
        self.assertContains(detalhe, "Violência")

        listagem = self.client.get("/campanhas/")
        self.assertContains(listagem, "16 anos")
        self.assertContains(listagem, "Conteúdo:")

    def test_campanha_antiga_sem_classificacao_pede_uma_ao_editar(self):
        campanha = self.criar_campanha(self.mestre, classificacao=None)
        pagina = self.client.get(f"/campanhas/{campanha.id}/editar/")
        self.assertContains(pagina, "Escolha uma faixa")
        resposta = self.client.post(
            f"/campanhas/{campanha.id}/editar/", dados_do_formulario(classificacao="")
        )
        self.assertEqual(resposta.status_code, 200)  # não salva sem escolher

    def test_mudar_a_classificacao_avisa_os_inscritos(self):
        jogador = self.criar_usuario("jogador")
        campanha = self.criar_campanha(self.mestre, jogadores_inscritos_emails=[jogador.email])
        self.client.post(
            f"/campanhas/{campanha.id}/editar/", dados_do_formulario(classificacao="18")
        )
        campanha.reload()
        self.assertEqual(campanha.classificacao, "18")
        self.assertIn("foi atualizada pelo mestre", self.textos_das_notificacoes(jogador)[0])


class RotuloDaSessaoTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")

    def rotulos(self, **extras):
        campanha = self.criar_campanha(self.mestre, **extras)
        pagina = Client().get(f"/campanhas/{campanha.id}/").content.decode()
        return "Próxima sessão" in pagina, "Sessão realizada em" in pagina

    def test_sessao_unica_no_futuro_e_a_proxima(self):
        amanha = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        self.assertEqual(self.rotulos(data_sessao=amanha), (True, False))

    def test_sessao_unica_que_ja_passou_aparece_como_realizada(self):
        ontem = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        self.assertEqual(self.rotulos(data_sessao=ontem), (False, True))

    def test_campanha_recorrente_sempre_mostra_a_proxima(self):
        mes_passado = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        self.assertEqual(
            self.rotulos(data_sessao=mes_passado, recorrencia="semanal"), (True, False)
        )

    def test_sem_data_continua_a_definir(self):
        self.assertEqual(self.rotulos(), (True, False))
