"""RF07 e RF02 - sair da mesa, encerrar e reabrir a campanha; RF08 - avisos
desses eventos e da exclusão da campanha."""

from django.test import Client

from core.base_testes import MongoTestCase

from .avaliacoes import avaliacoes_abertas
from .models import Campanha


class BaseCiclo(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.ana = self.criar_usuario("ana")
        self.beto = self.criar_usuario("beto")
        self.de_fora = self.criar_usuario("defora")
        self.campanha = self.criar_campanha(
            self.mestre,
            titulo="A Maldição de Strahd",
            max_jogadores=2,
            jogadores_inscritos_emails=[self.ana.email, self.beto.email],
            status="lotada",
        )

    def url(self, acao):
        return f"/campanhas/{self.campanha.id}/{acao}/"

    def recarregar(self):
        return Campanha.objects.get(id=self.campanha.id)

    def mensagens(self, resposta):
        return [str(m) for m in resposta.wsgi_request._messages]


class SairDaMesaTests(BaseCiclo):
    """RF07 - cancelar a própria inscrição."""

    def test_exige_login(self):
        resposta = Client().get(self.url("sair"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("login", resposta.url)

    def test_a_pagina_pede_confirmacao_e_nao_tira_ninguem(self):
        self.entrar(self.ana)
        resposta = self.client.get(self.url("sair"))
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "campanhas/confirmar_acao.html")
        self.assertContains(resposta, "A Maldição de Strahd")
        self.assertEqual(len(self.recarregar().jogadores_inscritos_emails), 2)

    def test_jogador_sai_da_mesa(self):
        self.entrar(self.ana)
        resposta = self.client.post(self.url("sair"))
        self.assertRedirects(
            resposta, f"/campanhas/{self.campanha.id}/", fetch_redirect_response=False
        )
        campanha = self.recarregar()
        self.assertEqual(campanha.jogadores_inscritos_emails, [self.beto.email])
        self.assertIn('Você saiu da campanha "A Maldição de Strahd".', self.mensagens(resposta))

    def test_sair_libera_a_vaga_e_reabre_a_mesa_lotada(self):
        self.assertEqual(self.recarregar().status, "lotada")
        self.entrar(self.ana)
        self.client.post(self.url("sair"))
        campanha = self.recarregar()
        self.assertEqual(campanha.vagas_livres, 1)
        self.assertEqual(campanha.status, "aberta")

    def test_sair_avisa_o_mestre_que_uma_vaga_abriu(self):
        self.entrar(self.ana)
        self.client.post(self.url("sair"))
        self.assertEqual(
            self.textos_das_notificacoes(self.mestre),
            ['ana saiu da sua campanha "A Maldição de Strahd". Uma vaga foi liberada.'],
        )

    def test_o_aviso_leva_para_a_campanha(self):
        self.entrar(self.ana)
        self.client.post(self.url("sair"))
        from notificacoes.models import Notificacao

        aviso = Notificacao.objects(destinatario_email=self.mestre.email).first()
        self.assertEqual(aviso.url, f"/campanhas/{self.campanha.id}/")

    def test_so_a_pessoa_que_saiu_perde_a_vaga(self):
        self.entrar(self.ana)
        self.client.post(self.url("sair"))
        self.assertEqual(self.textos_das_notificacoes(self.beto), [])
        self.assertIn(self.beto.email, self.recarregar().jogadores_inscritos_emails)

    def test_sair_de_mesa_encerrada_mantem_o_status_e_nao_fala_de_vaga(self):
        self.campanha.status = "encerrada"
        self.campanha.save()
        self.entrar(self.ana)
        self.client.post(self.url("sair"))
        self.assertEqual(self.recarregar().status, "encerrada")
        self.assertEqual(
            self.textos_das_notificacoes(self.mestre),
            ['ana saiu da sua campanha "A Maldição de Strahd".'],
        )

    def test_o_mestre_nao_pode_sair_da_propria_campanha(self):
        self.entrar(self.mestre)
        resposta = self.client.post(self.url("sair"))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.recarregar().mestre_email, self.mestre.email)
        self.assertEqual(len(self.recarregar().jogadores_inscritos_emails), 2)
        self.assertTrue(any("Você é o mestre" in m for m in self.mensagens(resposta)))

    def test_quem_nao_esta_inscrito_nao_mexe_na_mesa(self):
        self.entrar(self.de_fora)
        resposta = self.client.post(self.url("sair"))
        self.assertIn("Você não está inscrito nesta campanha.", self.mensagens(resposta))
        self.assertEqual(len(self.recarregar().jogadores_inscritos_emails), 2)
        self.assertEqual(self.textos_das_notificacoes(self.mestre), [])

    def test_campanha_inexistente_da_404(self):
        self.entrar(self.ana)
        self.assertEqual(self.client.post("/campanhas/000000000000000000000000/sair/").status_code, 404)
        self.assertEqual(self.client.post("/campanhas/invalido/sair/").status_code, 404)

    def test_depois_de_sair_a_pessoa_perde_o_acesso_ao_chat(self):
        self.entrar(self.ana)
        self.assertEqual(self.client.get(f"/chat/{self.campanha.id}/").status_code, 200)
        self.client.post(self.url("sair"))
        resposta = self.client.get(f"/chat/{self.campanha.id}/")
        self.assertRedirects(
            resposta, f"/campanhas/{self.campanha.id}/", fetch_redirect_response=False
        )

    def test_da_para_se_inscrever_de_novo_se_ainda_houver_vaga(self):
        self.entrar(self.ana)
        self.client.post(self.url("sair"))
        self.client.post(self.url("inscrever"))
        self.assertIn(self.ana.email, self.recarregar().jogadores_inscritos_emails)
        self.assertEqual(self.recarregar().status, "lotada")

    def test_o_botao_de_sair_so_aparece_para_quem_esta_inscrito(self):
        self.entrar(self.ana)
        self.assertContains(self.client.get(f"/campanhas/{self.campanha.id}/"), self.url("sair"))
        self.entrar(self.de_fora)
        self.assertNotContains(self.client.get(f"/campanhas/{self.campanha.id}/"), self.url("sair"))
        self.entrar(self.mestre)
        self.assertNotContains(self.client.get(f"/campanhas/{self.campanha.id}/"), self.url("sair"))

    def test_modelo_remove_e_recusa_quem_nao_esta(self):
        self.assertEqual(
            self.campanha.remover_jogador(self.de_fora.email),
            (False, "Você não está inscrito nesta campanha."),
        )
        self.assertEqual(
            self.campanha.remover_jogador(self.ana.email), (True, "Inscrição cancelada.")
        )


class InscricaoEmMesaEncerradaTests(BaseCiclo):
    """RF07 - mesa encerrada não aceita inscrição, mesmo com vaga sobrando."""

    def setUp(self):
        super().setUp()
        self.campanha.jogadores_inscritos_emails = [self.ana.email]
        self.campanha.status = "encerrada"
        self.campanha.save()

    def test_o_modelo_recusa(self):
        sucesso, mensagem = self.campanha.inscrever_jogador(self.de_fora.email)
        self.assertFalse(sucesso)
        self.assertIn("encerrada", mensagem)
        self.assertNotIn(self.de_fora.email, self.recarregar().jogadores_inscritos_emails)

    def test_a_view_recusa_e_nao_avisa_o_mestre(self):
        self.entrar(self.de_fora)
        resposta = self.client.post(self.url("inscrever"))
        self.assertTrue(any("encerrada" in m for m in self.mensagens(resposta)))
        self.assertEqual(self.recarregar().jogadores_inscritos_emails, [self.ana.email])
        self.assertEqual(self.textos_das_notificacoes(self.mestre), [])

    def test_quem_ja_estava_inscrito_continua_sendo_reconhecido(self):
        sucesso, mensagem = self.campanha.inscrever_jogador(self.ana.email)
        self.assertEqual((sucesso, mensagem), (False, "Você já está inscrito nesta campanha."))

    def test_o_detalhe_troca_o_botao_de_inscrever_pelo_aviso(self):
        self.entrar(self.de_fora)
        resposta = self.client.get(f"/campanhas/{self.campanha.id}/")
        self.assertContains(resposta, "não aceita novas inscrições")
        self.assertNotContains(resposta, self.url("inscrever"))

    def test_visitante_sem_login_ve_o_mesmo_aviso(self):
        resposta = Client().get(f"/campanhas/{self.campanha.id}/")
        self.assertContains(resposta, "não aceita novas inscrições")
        self.assertNotContains(resposta, "para se inscrever nesta campanha")

    def test_quem_esta_inscrito_ainda_pode_sair(self):
        self.entrar(self.ana)
        resposta = self.client.get(f"/campanhas/{self.campanha.id}/")
        self.assertContains(resposta, self.url("sair"))


class EncerrarEReabrirTests(BaseCiclo):
    """RF02 - o mestre encerra a mesa e, se quiser, a reabre."""

    def setUp(self):
        super().setUp()
        self.campanha.jogadores_inscritos_emails = [self.ana.email]
        self.campanha.status = "aberta"
        self.campanha.save()

    def test_encerrar_exige_login(self):
        resposta = Client().post(self.url("encerrar"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("login", resposta.url)
        self.assertEqual(self.recarregar().status, "aberta")

    def test_so_o_mestre_encerra(self):
        for pessoa in (self.ana, self.de_fora):
            self.entrar(pessoa)
            resposta = self.client.post(self.url("encerrar"))
            self.assertIn("Só o mestre da campanha pode encerrá-la.", self.mensagens(resposta))
        self.assertEqual(self.recarregar().status, "aberta")
        self.assertEqual(self.textos_das_notificacoes(self.ana), [])

    def test_a_pagina_pede_confirmacao_e_nao_encerra(self):
        self.entrar(self.mestre)
        resposta = self.client.get(self.url("encerrar"))
        self.assertTemplateUsed(resposta, "campanhas/confirmar_acao.html")
        self.assertContains(resposta, "Encerrar campanha")
        self.assertEqual(self.recarregar().status, "aberta")
        self.assertEqual(self.textos_das_notificacoes(self.ana), [])

    def test_encerrar_muda_o_status_e_avisa_so_os_inscritos(self):
        self.entrar(self.mestre)
        resposta = self.client.post(self.url("encerrar"))
        self.assertRedirects(
            resposta, f"/campanhas/{self.campanha.id}/", fetch_redirect_response=False
        )
        self.assertEqual(self.recarregar().status, "encerrada")
        avisos = self.textos_das_notificacoes(self.ana)
        self.assertEqual(len(avisos), 1)
        self.assertIn('"A Maldição de Strahd" foi encerrada pelo mestre', avisos[0])
        self.assertEqual(self.textos_das_notificacoes(self.mestre), [])
        self.assertEqual(self.textos_das_notificacoes(self.de_fora), [])

    def test_encerrar_libera_as_avaliacoes_mesmo_sem_data_de_sessao(self):
        self.assertFalse(avaliacoes_abertas(self.recarregar()))
        self.entrar(self.mestre)
        self.client.post(self.url("encerrar"))
        self.assertTrue(avaliacoes_abertas(self.recarregar()))

    def test_encerrar_de_novo_nao_avisa_outra_vez(self):
        self.entrar(self.mestre)
        self.client.post(self.url("encerrar"))
        resposta = self.client.post(self.url("encerrar"))
        self.assertIn("Esta campanha já está encerrada.", self.mensagens(resposta))
        self.assertEqual(len(self.textos_das_notificacoes(self.ana)), 1)

    def test_encerrar_lotada_tambem_funciona_e_mantem_os_inscritos(self):
        self.campanha.jogadores_inscritos_emails = [self.ana.email, self.beto.email]
        self.campanha.status = "lotada"
        self.campanha.save()
        self.entrar(self.mestre)
        self.client.post(self.url("encerrar"))
        campanha = self.recarregar()
        self.assertEqual(campanha.status, "encerrada")
        self.assertEqual(len(campanha.jogadores_inscritos_emails), 2)

    def test_reabrir_volta_a_aberta_quando_ha_vaga(self):
        self.campanha.status = "encerrada"
        self.campanha.save()
        self.entrar(self.mestre)
        resposta = self.client.post(self.url("reabrir"))
        self.assertIn("Campanha reaberta.", self.mensagens(resposta))
        self.assertEqual(self.recarregar().status, "aberta")

    def test_reabrir_volta_a_lotada_quando_nao_sobrou_vaga(self):
        self.campanha.jogadores_inscritos_emails = [self.ana.email, self.beto.email]
        self.campanha.status = "encerrada"
        self.campanha.save()
        self.entrar(self.mestre)
        self.client.post(self.url("reabrir"))
        self.assertEqual(self.recarregar().status, "lotada")

    def test_reabrir_avisa_os_inscritos(self):
        self.campanha.status = "encerrada"
        self.campanha.save()
        self.entrar(self.mestre)
        self.client.post(self.url("reabrir"))
        self.assertEqual(
            self.textos_das_notificacoes(self.ana),
            ['A campanha "A Maldição de Strahd" foi reaberta pelo mestre.'],
        )

    def test_reabrir_so_vale_com_post_e_so_para_o_mestre(self):
        self.campanha.status = "encerrada"
        self.campanha.save()

        self.entrar(self.mestre)
        self.client.get(self.url("reabrir"))
        self.assertEqual(self.recarregar().status, "encerrada")

        self.entrar(self.ana)
        resposta = self.client.post(self.url("reabrir"))
        self.assertIn("Só o mestre da campanha pode reabri-la.", self.mensagens(resposta))
        self.assertEqual(self.recarregar().status, "encerrada")

    def test_reabrir_uma_mesa_que_nao_esta_encerrada_nao_faz_nada(self):
        self.entrar(self.mestre)
        resposta = self.client.post(self.url("reabrir"))
        self.assertIn("Esta campanha não está encerrada.", self.mensagens(resposta))
        self.assertEqual(self.textos_das_notificacoes(self.ana), [])

    def test_o_botao_do_mestre_alterna_entre_encerrar_e_reabrir(self):
        self.entrar(self.mestre)
        aberta = self.client.get(f"/campanhas/{self.campanha.id}/")
        self.assertContains(aberta, self.url("encerrar"))
        self.assertNotContains(aberta, self.url("reabrir"))

        self.campanha.status = "encerrada"
        self.campanha.save()
        encerrada = self.client.get(f"/campanhas/{self.campanha.id}/")
        self.assertContains(encerrada, self.url("reabrir"))
        self.assertNotContains(encerrada, self.url("encerrar"))

    def test_so_o_mestre_ve_os_botoes_de_encerrar_e_reabrir(self):
        self.entrar(self.ana)
        resposta = self.client.get(f"/campanhas/{self.campanha.id}/")
        self.assertNotContains(resposta, self.url("encerrar"))
        self.assertNotContains(resposta, self.url("reabrir"))

    def test_mesa_encerrada_sai_da_tela_inicial_mas_continua_na_listagem(self):
        self.campanha.status = "encerrada"
        self.campanha.save()
        self.assertNotContains(Client().get("/"), "A Maldição de Strahd")
        listagem = Client().get("/campanhas/")
        self.assertContains(listagem, "A Maldição de Strahd")
        self.assertContains(listagem, "Encerrada")

    def test_mesa_encerrada_vai_para_a_secao_de_encerradas_do_mestre(self):
        self.entrar(self.mestre)
        self.client.post(self.url("encerrar"))
        resposta = self.client.get("/campanhas/minhas/")
        self.assertEqual([c.titulo for c in resposta.context["encerradas"]], ["A Maldição de Strahd"])
        self.assertEqual(list(resposta.context["ativas"]), [])


class ExcluirAvisaOsInscritosTests(BaseCiclo):
    """RF08 - quem estava inscrito é avisado quando a mesa é excluída."""

    def test_excluir_avisa_cada_inscrito(self):
        self.entrar(self.mestre)
        resposta = self.client.post(self.url("excluir"))
        self.assertRedirects(resposta, "/campanhas/", fetch_redirect_response=False)
        self.assertEqual(Campanha.objects(id=self.campanha.id).count(), 0)
        aviso = 'A campanha "A Maldição de Strahd" foi excluída pelo mestre.'
        self.assertEqual(self.textos_das_notificacoes(self.ana), [aviso])
        self.assertEqual(self.textos_das_notificacoes(self.beto), [aviso])

    def test_nem_o_mestre_nem_quem_nao_participa_recebem_o_aviso(self):
        self.entrar(self.mestre)
        self.client.post(self.url("excluir"))
        self.assertEqual(self.textos_das_notificacoes(self.mestre), [])
        self.assertEqual(self.textos_das_notificacoes(self.de_fora), [])

    def test_abrir_a_confirmacao_nao_avisa_ninguem(self):
        self.entrar(self.mestre)
        self.client.get(self.url("excluir"))
        self.assertEqual(Campanha.objects(id=self.campanha.id).count(), 1)
        self.assertEqual(self.textos_das_notificacoes(self.ana), [])

    def test_outra_pessoa_nao_exclui_nem_avisa(self):
        self.entrar(self.ana)
        self.client.post(self.url("excluir"))
        self.assertEqual(Campanha.objects(id=self.campanha.id).count(), 1)
        self.assertEqual(self.textos_das_notificacoes(self.beto), [])

    def test_mesa_sem_inscritos_exclui_sem_gerar_avisos(self):
        vazia = self.criar_campanha(self.mestre, titulo="Vazia")
        self.entrar(self.mestre)
        self.client.post(f"/campanhas/{vazia.id}/excluir/")
        self.assertEqual(Campanha.objects(id=vazia.id).count(), 0)
        from notificacoes.models import Notificacao

        self.assertEqual(Notificacao.objects.count(), 0)
