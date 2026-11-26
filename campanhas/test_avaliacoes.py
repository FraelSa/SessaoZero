"""RF06 - avaliações de mestres e jogadores."""

import datetime

from django.test import Client

from accounts.models import Usuario
from core.base_testes import MongoTestCase

from .avaliacoes import avaliacoes_abertas, reputacao
from .models import Avaliacao, Campanha

AGORA = datetime.datetime.utcnow
ONTEM = lambda: AGORA() - datetime.timedelta(days=1)  # noqa: E731
AMANHA = lambda: AGORA() + datetime.timedelta(days=1)  # noqa: E731


class BaseAvaliacao(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.ana = self.criar_usuario("ana")
        self.beto = self.criar_usuario("beto")
        self.de_fora = self.criar_usuario("defora")
        self.campanha = self.criar_campanha(
            self.mestre,
            data_sessao=ONTEM(),
            jogadores_inscritos_emails=[self.ana.email, self.beto.email],
        )

    def avaliar(self, quem, username, nota="5", comentario="", campanha=None, cliente=None):
        cliente = cliente or self.client
        if quem is not None:
            self.entrar(quem)
        campanha = campanha or self.campanha
        return cliente.post(
            f"/campanhas/{campanha.id}/avaliar/{username}/",
            {"nota": nota, "comentario": comentario},
        )

    def mensagens(self, resposta):
        return [str(m) for m in resposta.wsgi_request._messages]


class QuandoAvaliarTests(BaseAvaliacao):
    def test_abre_depois_da_data_da_primeira_sessao(self):
        self.assertTrue(avaliacoes_abertas(self.campanha))

    def test_fechada_antes_da_primeira_sessao(self):
        self.campanha.data_sessao = AMANHA()
        self.assertFalse(avaliacoes_abertas(self.campanha))

    def test_fechada_sem_data_de_sessao(self):
        self.campanha.data_sessao = None
        self.assertFalse(avaliacoes_abertas(self.campanha))

    def test_campanha_encerrada_abre_mesmo_sem_data(self):
        self.campanha.data_sessao = None
        self.campanha.status = "encerrada"
        self.assertTrue(avaliacoes_abertas(self.campanha))

    def test_nao_salva_avaliacao_antes_da_primeira_sessao(self):
        self.campanha.data_sessao = AMANHA()
        self.campanha.save()
        resposta = self.avaliar(self.ana, "mestre")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Avaliacao.objects.count(), 0)
        self.assertIn("abrem depois da primeira sessão", self.mensagens(resposta)[-1])

    def test_antes_da_primeira_sessao_a_tela_explica_e_nao_mostra_formularios(self):
        self.campanha.data_sessao = AMANHA()
        self.campanha.save()
        self.entrar(self.ana)
        pagina = self.client.get(f"/campanhas/{self.campanha.id}/").content.decode()
        self.assertIn("As avaliações abrem depois da primeira sessão", pagina)
        self.assertNotIn(f"/campanhas/{self.campanha.id}/avaliar/", pagina)


class QuemPodeAvaliarTests(BaseAvaliacao):
    def test_jogador_avalia_o_mestre(self):
        self.avaliar(self.ana, "mestre", nota="4", comentario="Mesa organizada.")
        a = Avaliacao.objects.get()
        self.assertEqual(
            (a.avaliador_email, a.avaliado_email, a.papel_avaliado, a.nota),
            (self.ana.email, self.mestre.email, "mestre", 4),
        )
        self.assertEqual(a.comentario, "Mesa organizada.")
        self.assertEqual((a.avaliador_username, a.avaliado_username), ("ana", "mestre"))
        self.assertEqual(a.campanha_titulo, self.campanha.titulo)

    def test_mestre_avalia_um_jogador(self):
        self.avaliar(self.mestre, "ana", nota="5")
        a = Avaliacao.objects.get()
        self.assertEqual((a.avaliado_email, a.papel_avaliado), (self.ana.email, "jogador"))

    def test_jogador_avalia_outro_jogador(self):
        self.avaliar(self.ana, "beto", nota="3")
        a = Avaliacao.objects.get()
        self.assertEqual((a.avaliado_email, a.papel_avaliado), (self.beto.email, "jogador"))

    def test_ninguem_avalia_a_si_mesmo(self):
        resposta = self.avaliar(self.ana, "ana")
        self.assertEqual(Avaliacao.objects.count(), 0)
        self.assertIn("a si mesmo", self.mensagens(resposta)[0])

    def test_quem_nao_participa_nao_avalia(self):
        resposta = self.avaliar(self.de_fora, "mestre")
        self.assertEqual(Avaliacao.objects.count(), 0)
        self.assertIn("participa", self.mensagens(resposta)[0])

    def test_nao_se_avalia_quem_nao_participa(self):
        resposta = self.avaliar(self.ana, "defora")
        self.assertEqual(Avaliacao.objects.count(), 0)
        self.assertIn("não participa", self.mensagens(resposta)[0])

    def test_inscricao_removida_tira_a_pessoa_dos_alvos(self):
        self.campanha.jogadores_inscritos_emails = [self.beto.email]
        self.campanha.save()
        self.avaliar(self.mestre, "ana")
        self.assertEqual(Avaliacao.objects.count(), 0)

    def test_visitante_anonimo_vai_para_o_login(self):
        resposta = self.avaliar(None, "mestre", cliente=Client())
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/contas/login/", resposta["Location"])
        self.assertEqual(Avaliacao.objects.count(), 0)

    def test_get_nao_cria_avaliacao(self):
        self.entrar(self.ana)
        resposta = self.client.get(f"/campanhas/{self.campanha.id}/avaliar/mestre/")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Avaliacao.objects.count(), 0)

    def test_campanha_inexistente_da_404(self):
        self.entrar(self.ana)
        resposta = self.client.post("/campanhas/000000000000000000000000/avaliar/mestre/", {"nota": "5"})
        self.assertEqual(resposta.status_code, 404)


class DadosDaAvaliacaoTests(BaseAvaliacao):
    def test_nota_fora_de_1_a_5_e_recusada(self):
        for nota in ("0", "6", "-1", "abc", ""):
            with self.subTest(nota=nota):
                self.avaliar(self.ana, "mestre", nota=nota)
        self.assertEqual(Avaliacao.objects.count(), 0)

    def test_aceita_todas_as_notas_de_1_a_5(self):
        for nota in range(1, 6):
            with self.subTest(nota=nota):
                Avaliacao.drop_collection()
                self.avaliar(self.ana, "mestre", nota=str(nota))
                self.assertEqual(Avaliacao.objects.get().nota, nota)

    def test_comentario_e_opcional(self):
        self.avaliar(self.ana, "mestre", nota="5", comentario="")
        self.assertEqual(Avaliacao.objects.get().comentario, "")

    def test_comentario_com_mais_de_500_caracteres_e_recusado(self):
        self.avaliar(self.ana, "mestre", comentario="a" * 501)
        self.assertEqual(Avaliacao.objects.count(), 0)

    def test_comentario_de_500_caracteres_passa(self):
        self.avaliar(self.ana, "mestre", comentario="a" * 500)
        self.assertEqual(len(Avaliacao.objects.get().comentario), 500)

    def test_comentario_ofensivo_e_barrado_e_registrado_na_moderacao(self):
        from moderacao.models import ConteudoBloqueado

        self.avaliar(self.ana, "mestre", comentario="você é um idiota")
        self.assertEqual(Avaliacao.objects.count(), 0)
        bloqueio = ConteudoBloqueado.objects.get()
        self.assertEqual(bloqueio.autor_email, self.ana.email)
        self.assertEqual(bloqueio.origem, f"avaliacao:{self.campanha.id}")

    def test_comentario_ofensivo_nao_trava_a_nota_seguinte(self):
        self.avaliar(self.ana, "mestre", comentario="você é um idiota")
        self.avaliar(self.ana, "mestre", nota="4", comentario="Boa mesa.")
        self.assertEqual(Avaliacao.objects.get().nota, 4)


class AtualizarAvaliacaoTests(BaseAvaliacao):
    def test_avaliar_de_novo_atualiza_em_vez_de_duplicar(self):
        self.avaliar(self.ana, "mestre", nota="2", comentario="Começou mal.")
        resposta = self.avaliar(self.ana, "mestre", nota="5", comentario="Melhorou muito.")
        a = Avaliacao.objects.get()
        self.assertEqual((a.nota, a.comentario), (5, "Melhorou muito."))
        self.assertIn("atualizada", self.mensagens(resposta)[-1])

    def test_so_a_primeira_avaliacao_notifica(self):
        self.avaliar(self.ana, "mestre", nota="2")
        self.avaliar(self.ana, "mestre", nota="5")
        avisos = self.textos_das_notificacoes(self.mestre)
        self.assertEqual(len(avisos), 1)
        self.assertIn("ana", avisos[0])
        self.assertIn(self.campanha.titulo, avisos[0])

    def test_o_aviso_leva_ao_perfil_publico_de_quem_foi_avaliado(self):
        from notificacoes.models import Notificacao

        self.avaliar(self.ana, "mestre")
        self.assertEqual(Notificacao.objects.get().url, "/contas/u/mestre/")

    def test_cada_avaliador_tem_a_sua_propria_avaliacao(self):
        self.avaliar(self.ana, "mestre", nota="5")
        self.avaliar(self.beto, "mestre", nota="3")
        self.assertEqual(Avaliacao.objects.count(), 2)

    def test_a_mesma_pessoa_avalia_o_mesmo_alvo_em_campanhas_diferentes(self):
        outra = self.criar_campanha(
            self.mestre,
            titulo="Outra mesa",
            data_sessao=ONTEM(),
            jogadores_inscritos_emails=[self.ana.email],
        )
        self.avaliar(self.ana, "mestre", nota="5")
        self.avaliar(self.ana, "mestre", nota="1", campanha=outra)
        self.assertEqual(Avaliacao.objects.count(), 2)


class ReputacaoTests(BaseAvaliacao):
    def test_sem_avaliacoes_nao_ha_media(self):
        self.assertEqual(reputacao(self.mestre.email), {"media": None, "total": 0})

    def test_media_das_notas_recebidas(self):
        self.avaliar(self.ana, "mestre", nota="5")
        self.avaliar(self.beto, "mestre", nota="4")
        self.assertEqual(reputacao(self.mestre.email), {"media": 4.5, "total": 2})

    def test_reputacao_separa_mestre_e_jogador(self):
        outra = self.criar_campanha(
            self.ana,
            titulo="Mesa da Ana",
            data_sessao=ONTEM(),
            jogadores_inscritos_emails=[self.mestre.email],
        )
        self.avaliar(self.beto, "mestre", nota="5")          # mestre como mestre
        self.avaliar(self.ana, "mestre", nota="1", campanha=outra)  # mestre como jogador
        self.assertEqual(reputacao(self.mestre.email, "mestre"), {"media": 5.0, "total": 1})
        self.assertEqual(reputacao(self.mestre.email, "jogador"), {"media": 1.0, "total": 1})
        self.assertEqual(reputacao(self.mestre.email), {"media": 3.0, "total": 2})

    def test_media_e_arredondada_para_uma_casa(self):
        self.avaliar(self.ana, "mestre", nota="5")
        self.avaliar(self.beto, "mestre", nota="4")
        self.campanha.jogadores_inscritos_emails.append(self.de_fora.email)
        self.campanha.save()
        self.avaliar(self.de_fora, "mestre", nota="4")
        self.assertEqual(reputacao(self.mestre.email)["media"], 4.3)

    def test_excluir_a_campanha_nao_apaga_a_reputacao(self):
        self.avaliar(self.ana, "mestre", nota="5")
        self.entrar(self.mestre)
        self.client.post(f"/campanhas/{self.campanha.id}/excluir/")
        self.assertEqual(Campanha.objects.count(), 0)
        self.assertEqual(reputacao(self.mestre.email), {"media": 5.0, "total": 1})
        self.assertEqual(Avaliacao.objects.get().campanha_titulo, self.campanha.titulo)


class TelaDaCampanhaTests(BaseAvaliacao):
    def pagina(self, quem=None):
        if quem is not None:
            self.entrar(quem)
        resposta = self.client.get(f"/campanhas/{self.campanha.id}/")
        self.assertEqual(resposta.status_code, 200)
        return resposta.content.decode()

    def test_participante_ve_o_formulario_dos_outros_participantes(self):
        pagina = self.pagina(self.ana)
        self.assertIn('id="avaliacoes"', pagina)
        for username in ("mestre", "beto"):
            self.assertIn(f"/campanhas/{self.campanha.id}/avaliar/{username}/", pagina)
        self.assertNotIn(f"/campanhas/{self.campanha.id}/avaliar/ana/", pagina)

    def test_mestre_ve_os_jogadores(self):
        pagina = self.pagina(self.mestre)
        for username in ("ana", "beto"):
            self.assertIn(f"/campanhas/{self.campanha.id}/avaliar/{username}/", pagina)

    def test_quem_nao_participa_nao_ve_o_formulario(self):
        self.assertNotIn('id="avaliacoes"', self.pagina(self.de_fora))

    def test_visitante_anonimo_nao_ve_o_formulario(self):
        self.assertNotIn('id="avaliacoes"', self.pagina())

    def test_tela_mostra_a_nota_que_a_pessoa_ja_deu(self):
        self.avaliar(self.ana, "mestre", nota="4", comentario="Boa mesa.")
        pagina = self.pagina(self.ana)
        self.assertIn("Boa mesa.", pagina)
        self.assertRegex(pagina, r'<option value="4"\s+selected')

    def test_nome_do_mestre_leva_ao_perfil_com_a_reputacao(self):
        self.avaliar(self.ana, "mestre", nota="4")
        pagina = self.pagina(self.de_fora)
        self.assertIn("/contas/u/mestre/", pagina)
        self.assertIn("4,0", pagina)


class PerfilPublicoTests(BaseAvaliacao):
    def test_perfil_e_publico(self):
        resposta = Client().get("/contas/u/mestre/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "mestre")

    def test_usuario_inexistente_da_404(self):
        self.assertEqual(Client().get("/contas/u/ninguem/").status_code, 404)

    def test_conta_inativa_da_404(self):
        self.ana.ativo = False
        self.ana.save()
        self.assertEqual(Client().get("/contas/u/ana/").status_code, 404)

    def test_perfil_nao_vaza_o_email(self):
        self.avaliar(self.ana, "mestre", nota="5", comentario="Ótima mesa.")
        pagina = Client().get("/contas/u/mestre/").content.decode()
        for email in (self.mestre.email, self.ana.email, self.beto.email):
            self.assertNotIn(email, pagina)

    def test_perfil_lista_as_avaliacoes_recebidas(self):
        self.avaliar(self.ana, "mestre", nota="4", comentario="Ótima mesa.")
        pagina = Client().get("/contas/u/mestre/").content.decode()
        self.assertIn("Ótima mesa.", pagina)
        self.assertIn(self.campanha.titulo, pagina)
        self.assertIn("/contas/u/ana/", pagina)

    def test_perfil_sem_avaliacoes_abre(self):
        self.assertEqual(Client().get("/contas/u/beto/").status_code, 200)

    def test_avaliacao_dada_nao_aparece_no_perfil_de_quem_avaliou(self):
        self.avaliar(self.ana, "mestre", comentario="Texto escrito pela Ana.")
        pagina = Client().get("/contas/u/ana/").content.decode()
        self.assertNotIn("Texto escrito pela Ana.", pagina)


class AvaliacoesEExclusaoDeContaTests(BaseAvaliacao):
    def excluir(self, usuario):
        self.entrar(usuario)
        self.client.post("/contas/excluir/", {"senha": "Senha-forte-123", "confirmacao": "on"})
        self.assertIsNone(Usuario.objects(email=usuario.email).first())

    def test_avaliacoes_recebidas_por_quem_saiu_sao_apagadas(self):
        self.avaliar(self.ana, "beto", nota="5")
        self.avaliar(self.mestre, "beto", nota="4")
        self.excluir(self.beto)
        self.assertEqual(Avaliacao.objects.count(), 0)

    def test_avaliacoes_dadas_por_quem_saiu_ficam_anonimas(self):
        self.avaliar(self.ana, "mestre", nota="5", comentario="Gostei.")
        self.excluir(self.ana)
        a = Avaliacao.objects.get()
        self.assertEqual(a.nota, 5)
        self.assertEqual(a.avaliador_username, "[conta excluída]")
        self.assertNotIn(self.ana.email, a.avaliador_email)
        self.assertEqual(reputacao(self.mestre.email), {"media": 5.0, "total": 1})

    def test_dois_avaliadores_que_saem_nao_colidem_no_indice_unico(self):
        self.avaliar(self.ana, "mestre", nota="5")
        self.avaliar(self.beto, "mestre", nota="3")
        self.excluir(self.ana)
        self.excluir(self.beto)
        self.assertEqual(Avaliacao.objects.count(), 2)
        self.assertEqual(reputacao(self.mestre.email), {"media": 4.0, "total": 2})

    def test_perfil_do_mestre_mostra_avaliador_excluido_sem_link(self):
        self.avaliar(self.ana, "mestre", nota="5", comentario="Gostei.")
        self.excluir(self.ana)
        pagina = Client().get("/contas/u/mestre/").content.decode()
        self.assertIn("[conta excluída]", pagina)
        self.assertNotIn("/contas/u/[conta", pagina)

    def test_mestre_que_sai_leva_as_campanhas_mas_as_avaliacoes_dos_outros_somem(self):
        self.avaliar(self.ana, "mestre", nota="5")
        self.excluir(self.mestre)
        self.assertEqual(Avaliacao.objects.count(), 0)
