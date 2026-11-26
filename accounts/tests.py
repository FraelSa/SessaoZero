import datetime

from django.test import Client

from campanhas.models import Campanha, Comentario
from chat.models import MensagemChat
from core.base_testes import SENHA_PADRAO, MongoTestCase
from moderacao.models import ConteudoBloqueado
from notificacoes.models import Notificacao

from .exclusao import AUTOR_REMOVIDO, EMAIL_REMOVIDO
from .models import CadastroPendente, FotoPerfil, Usuario

NOVA_SENHA = "Outra-senha-forte-456"


class MinhaContaTests(MongoTestCase):
    """RF01 - trocar a senha estando logado."""

    def setUp(self):
        super().setUp()
        self.usuario = self.criar_usuario("ana")
        self.entrar(self.usuario)

    def trocar(self, **mudancas):
        dados = {
            "senha_atual": SENHA_PADRAO,
            "nova_senha": NOVA_SENHA,
            "confirmar_nova_senha": NOVA_SENHA,
        }
        dados.update(mudancas)
        return self.client.post("/contas/conta/", dados)

    def test_pagina_exige_login(self):
        resposta = Client().get("/contas/conta/")
        self.assertRedirects(resposta, "/contas/login/", fetch_redirect_response=False)

    def test_menu_tem_o_link_minha_conta(self):
        self.assertContains(self.client.get("/campanhas/"), "/contas/conta/")

    def test_troca_de_senha(self):
        resposta = self.trocar()
        self.assertRedirects(resposta, "/contas/conta/", fetch_redirect_response=False)
        self.usuario.reload()
        self.assertTrue(self.usuario.checar_senha(NOVA_SENHA))
        self.assertFalse(self.usuario.checar_senha(SENHA_PADRAO))

    def test_senha_atual_errada_nao_troca(self):
        resposta = self.trocar(senha_atual="errada-errada")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "A senha atual não confere.")
        self.usuario.reload()
        self.assertTrue(self.usuario.checar_senha(SENHA_PADRAO))

    def test_confirmacao_diferente_nao_troca(self):
        resposta = self.trocar(confirmar_nova_senha="diferente-123456")
        self.assertContains(resposta, "As senhas não coincidem.")
        self.usuario.reload()
        self.assertTrue(self.usuario.checar_senha(SENHA_PADRAO))

    def test_senha_fraca_e_recusada(self):
        resposta = self.trocar(nova_senha="123", confirmar_nova_senha="123")
        self.assertEqual(resposta.status_code, 200)
        self.usuario.reload()
        self.assertTrue(self.usuario.checar_senha(SENHA_PADRAO))

    def test_trocar_a_senha_invalida_link_de_recuperacao_pendente(self):
        self.usuario.token_recuperacao_senha = "token-antigo"
        self.usuario.token_recuperacao_expira_em = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        self.usuario.save()
        self.trocar()
        self.usuario.reload()
        self.assertIsNone(self.usuario.token_recuperacao_senha)
        self.assertIsNone(self.usuario.token_recuperacao_expira_em)


class ExclusaoDeContaTests(MongoTestCase):
    """RF01 - excluir a própria conta."""

    def setUp(self):
        super().setUp()
        self.ana = self.criar_usuario("ana")
        self.mestre = self.criar_usuario("mestre")
        self.outro = self.criar_usuario("outro")
        self.entrar(self.ana)

    def excluir(self, **mudancas):
        dados = {"senha": SENHA_PADRAO, "confirmacao": "on"}
        dados.update(mudancas)
        return self.client.post("/contas/excluir/", dados)

    def test_pagina_exige_login(self):
        self.assertRedirects(
            Client().get("/contas/excluir/"), "/contas/login/", fetch_redirect_response=False
        )

    def test_tela_de_confirmacao_conta_o_que_sera_afetado(self):
        self.criar_campanha(self.ana, titulo="Minha mesa")
        self.criar_campanha(self.mestre, titulo="Mesa alheia", jogadores_inscritos_emails=[self.ana.email])
        pagina = self.client.get("/contas/excluir/")
        self.assertContains(pagina, "não pode ser desfeita")
        self.assertContains(pagina, "<strong>1</strong> campanha que você mestra")
        self.assertContains(pagina, "você sai de <strong>1</strong> campanha")

    def test_senha_errada_nao_exclui(self):
        resposta = self.excluir(senha="errada-errada")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Senha incorreta.")
        self.assertEqual(Usuario.objects(email=self.ana.email).count(), 1)

    def test_sem_marcar_a_confirmacao_nao_exclui(self):
        resposta = self.client.post("/contas/excluir/", {"senha": SENHA_PADRAO})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Usuario.objects(email=self.ana.email).count(), 1)

    def test_exclusao_remove_o_usuario_encerra_a_sessao_e_avisa(self):
        resposta = self.excluir()
        self.assertRedirects(resposta, "/", fetch_redirect_response=False)
        self.assertEqual(Usuario.objects(email=self.ana.email).count(), 0)
        self.assertNotIn("usuario_id", self.client.session)
        # A mesma sessão já não dá acesso a nada.
        self.assertRedirects(
            self.client.get("/contas/conta/"), "/contas/login/", fetch_redirect_response=False
        )

    def test_nao_e_possivel_entrar_de_novo_com_a_conta_excluida(self):
        self.excluir()
        resposta = Client().post(
            "/contas/login/", {"email": self.ana.email, "senha": SENHA_PADRAO}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("usuario_id", resposta.client.session)

    def test_campanhas_do_mestre_somem_com_o_chat_e_os_inscritos_sao_avisados(self):
        campanha = self.criar_campanha(
            self.ana,
            titulo="Mesa da Ana",
            jogadores_inscritos_emails=[self.outro.email],
        )
        MensagemChat(
            campanha_id=str(campanha.id), autor_email=self.outro.email,
            autor_username="outro", texto="oi",
        ).save()
        outra = self.criar_campanha(self.mestre, titulo="Mesa de outro mestre")

        self.excluir()

        self.assertEqual(Campanha.objects(titulo="Mesa da Ana").count(), 0)
        self.assertEqual(MensagemChat.objects(campanha_id=str(campanha.id)).count(), 0)
        self.assertEqual(Campanha.objects(id=outra.id).count(), 1)
        avisos = self.textos_das_notificacoes(self.outro)
        self.assertEqual(len(avisos), 1)
        self.assertIn('"Mesa da Ana" foi encerrada', avisos[0])

    def test_inscricao_e_removida_a_vaga_volta_e_a_mesa_lotada_reabre(self):
        campanha = self.criar_campanha(
            self.mestre,
            max_jogadores=2,
            status="lotada",
            jogadores_inscritos_emails=[self.ana.email, self.outro.email],
        )
        self.excluir()
        campanha.reload()
        self.assertEqual(campanha.jogadores_inscritos_emails, [self.outro.email])
        self.assertEqual(campanha.vagas_livres, 1)
        self.assertEqual(campanha.status, "aberta")
        avisos = self.textos_das_notificacoes(self.mestre)
        self.assertEqual(len(avisos), 1)
        self.assertIn("ana excluiu a conta", avisos[0])

    def test_campanha_encerrada_continua_encerrada_depois_que_alguem_sai(self):
        campanha = self.criar_campanha(
            self.mestre, status="encerrada", jogadores_inscritos_emails=[self.ana.email]
        )
        self.excluir()
        campanha.reload()
        self.assertEqual(campanha.status, "encerrada")

    def test_comentarios_ficam_sem_identificacao(self):
        campanha = self.criar_campanha(self.mestre)
        campanha.comentarios = [
            Comentario(autor_email=self.ana.email, autor_username="ana", texto="Quero jogar!"),
            Comentario(autor_email=self.outro.email, autor_username="outro", texto="Eu também"),
        ]
        campanha.save()
        self.excluir()
        campanha.reload()
        ana, outro = campanha.comentarios
        self.assertEqual((ana.autor_email, ana.autor_username), (EMAIL_REMOVIDO, AUTOR_REMOVIDO))
        self.assertEqual(ana.texto, "Quero jogar!")
        self.assertEqual((outro.autor_email, outro.autor_username), (self.outro.email, "outro"))

    def test_detalhe_da_campanha_abre_com_comentario_de_conta_excluida(self):
        campanha = self.criar_campanha(self.mestre)
        campanha.comentarios = [
            Comentario(autor_email=self.ana.email, autor_username="ana", texto="Quero jogar!")
        ]
        campanha.save()
        self.excluir()
        pagina = Client().get(f"/campanhas/{campanha.id}/")
        self.assertContains(pagina, AUTOR_REMOVIDO)
        self.assertContains(pagina, "Quero jogar!")

    def test_mensagens_de_chat_e_moderacao_ficam_sem_identificacao(self):
        campanha = self.criar_campanha(self.mestre, jogadores_inscritos_emails=[self.ana.email])
        MensagemChat(
            campanha_id=str(campanha.id), autor_email=self.ana.email,
            autor_username="ana", texto="Boa noite, mesa",
        ).save()
        ConteudoBloqueado(
            autor_email=self.ana.email, texto_original="xxx", motivo="teste", origem="comentario"
        ).save()
        self.excluir()
        mensagem = MensagemChat.objects.get(campanha_id=str(campanha.id))
        self.assertEqual((mensagem.autor_email, mensagem.autor_username), (EMAIL_REMOVIDO, AUTOR_REMOVIDO))
        self.assertEqual(mensagem.texto, "Boa noite, mesa")
        self.assertEqual(ConteudoBloqueado.objects.get().autor_email, EMAIL_REMOVIDO)

    def test_dados_proprios_somem(self):
        Notificacao(destinatario_email=self.ana.email, texto="oi").save()
        Notificacao(destinatario_email=self.outro.email, texto="oi").save()
        FotoPerfil(usuario_id=str(self.ana.id), dados=b"\x89PNG").save()
        CadastroPendente(
            email=self.ana.email, username="ana", senha_hash="x",
            token="t", expira_em=datetime.datetime.utcnow(),
        ).save()
        self.excluir()
        self.assertEqual(Notificacao.objects(destinatario_email=self.ana.email).count(), 0)
        self.assertEqual(Notificacao.objects(destinatario_email=self.outro.email).count(), 1)
        self.assertEqual(FotoPerfil.objects.count(), 0)
        self.assertEqual(CadastroPendente.objects.count(), 0)

    def test_usuario_pode_se_cadastrar_de_novo_com_o_mesmo_email(self):
        self.excluir()
        novo = self.criar_usuario("ana", email="ana@exemplo.com")
        self.assertEqual(Usuario.objects(email="ana@exemplo.com").count(), 1)
        self.assertNotEqual(novo.id, self.ana.id)


class FusoNasPreferenciasTests(MongoTestCase):
    """RD04 - o fuso escolhido vale em todas as telas."""

    def setUp(self):
        super().setUp()
        self.usuario = self.criar_usuario("ana")
        self.entrar(self.usuario)

    def salvar(self, fuso):
        return self.client.post(
            "/contas/preferencias/",
            {"fuso_horario": fuso, "sistemas_favoritos": ["D&D 5e"], "estilos_favoritos": ["Terror"]},
        )

    def test_fuso_padrao_e_bahia(self):
        self.assertEqual(self.usuario.fuso_horario, "America/Bahia")
        pagina = self.client.get("/contas/preferencias/")
        self.assertContains(pagina, '<option value="America/Bahia" selected>')

    def test_salvar_o_fuso(self):
        resposta = self.salvar("America/Manaus")
        self.assertEqual(resposta.status_code, 302)
        self.usuario.reload()
        self.assertEqual(self.usuario.fuso_horario, "America/Manaus")
        # E a recomendação continua recebendo só sistemas e estilos.
        self.assertEqual(
            self.usuario.preferencias,
            {"sistemas_favoritos": ["D&D 5e"], "estilos_favoritos": ["Terror"]},
        )

    def test_fuso_desconhecido_e_recusado(self):
        resposta = self.salvar("Mars/Olympus_Mons")
        self.assertEqual(resposta.status_code, 200)
        self.usuario.reload()
        self.assertEqual(self.usuario.fuso_horario, "America/Bahia")

    def test_usuario_antigo_com_fuso_invalido_nao_derruba_as_paginas(self):
        Usuario.objects(id=self.usuario.id).update(set__fuso_horario="Lugar/Nenhum")
        self.assertEqual(self.client.get("/campanhas/").status_code, 200)
        self.assertEqual(self.client.get("/contas/preferencias/").status_code, 200)

    def test_usuario_antigo_sem_o_campo_usa_o_padrao(self):
        Usuario._get_collection().update_one(
            {"_id": self.usuario.id}, {"$unset": {"fuso_horario": ""}}
        )
        self.assertEqual(self.client.get("/campanhas/").status_code, 200)
        self.assertContains(
            self.client.get("/contas/preferencias/"), '<option value="America/Bahia" selected>'
        )

    def test_hora_do_comentario_segue_o_fuso_de_quem_ve(self):
        mestre = self.criar_usuario("mestre")
        campanha = self.criar_campanha(mestre)
        campanha.comentarios = [
            Comentario(
                autor_email=mestre.email, autor_username="mestre", texto="Bem-vindos",
                criado_em=datetime.datetime(2026, 10, 30, 0, 0),
            )
        ]
        campanha.save()
        url = f"/campanhas/{campanha.id}/"
        self.assertContains(self.client.get(url), "29/10/2026, 21:00")  # Bahia, UTC-3
        self.salvar("America/Manaus")
        self.assertContains(self.client.get(url), "29/10/2026, 20:00")  # Manaus, UTC-4
