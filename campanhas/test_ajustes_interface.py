"""Testes dos ajustes de interface: regras e indicador de senha, "Sistema
Próprio", "Minhas campanhas", marcação das campanhas da pessoa e sino de
notificações."""

from core.base_testes import SENHA_PADRAO, MongoTestCase
from notificacoes.models import Notificacao

from .models import Campanha
from .tests import dados_do_formulario


def dados_de_cadastro(**mudancas):
    dados = {
        "username": "novato",
        "email": "novato@exemplo.com",
        "senha": SENHA_PADRAO,
        "confirmar_senha": SENHA_PADRAO,
        "aceite_politica": "on",
    }
    dados.update(mudancas)
    return dados


class SenhaNoCadastroTests(MongoTestCase):
    def test_pagina_mostra_os_limites_e_o_indicador(self):
        resposta = self.client.get("/contas/cadastro/")
        self.assertContains(resposta, "De 8 a 128 caracteres")
        self.assertContains(resposta, 'maxlength="128"')
        self.assertContains(resposta, "data-forca-senha")
        self.assertContains(resposta, "forca_senha.js")

    def test_cada_erro_de_senha_fica_em_um_item_proprio(self):
        resposta = self.client.post(
            "/contas/cadastro/", dados_de_cadastro(senha="1234", confirmar_senha="1234")
        )
        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode()
        self.assertIn('<ul class="campo__erros">', conteudo)
        self.assertIn("<li>Esta senha é muito curta", conteudo)
        self.assertIn("<li>Esta senha é muito comum.</li>", conteudo)
        self.assertIn("<li>Esta senha é inteiramente numérica.</li>", conteudo)

    def test_senha_acima_do_maximo_e_recusada(self):
        longa = "Ab1-" * 33  # 132 caracteres
        resposta = self.client.post(
            "/contas/cadastro/", dados_de_cadastro(senha=longa, confirmar_senha=longa)
        )
        self.assertContains(resposta, "no máximo 128 caracteres")

    def test_verificar_senha_diz_quais_regras_a_senha_cumpre(self):
        def verificar(senha):
            return self.client.post("/contas/verificar-senha/", {"senha": senha}).json()

        self.assertEqual(
            verificar("12345678"),
            {"tamanho": True, "letras": False, "comum": False, "valida": False},
        )
        self.assertEqual(verificar("Ab1")["tamanho"], False)
        self.assertEqual(verificar("Ab1" * 50)["tamanho"], False)  # 150 caracteres
        self.assertEqual(
            verificar(SENHA_PADRAO),
            {"tamanho": True, "letras": True, "comum": True, "valida": True},
        )

    def test_verificar_senha_so_aceita_post(self):
        self.assertEqual(self.client.get("/contas/verificar-senha/").status_code, 405)


class SistemaProprioTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.entrar(self.mestre)

    def test_opcao_outro_virou_sistema_proprio(self):
        resposta = self.client.get("/campanhas/nova/")
        self.assertContains(resposta, '<option value="Sistema Próprio">Sistema Próprio</option>')
        self.assertNotContains(resposta, '<option value="Outro">')
        self.assertContains(resposta, 'name="sistema_proprio"')

    def test_grava_o_nome_digitado_para_o_sistema_proprio(self):
        self.client.post(
            "/campanhas/nova/",
            dados_do_formulario(sistema_rpg="Sistema Próprio", sistema_proprio="  Reinos de Ferro  "),
        )
        campanha = Campanha.objects.get()
        self.assertEqual(campanha.sistema_rpg, "Reinos de Ferro")
        self.assertTrue(campanha.tem_sistema_proprio)

    def test_sistema_proprio_sem_nome_e_recusado(self):
        resposta = self.client.post(
            "/campanhas/nova/", dados_do_formulario(sistema_rpg="Sistema Próprio")
        )
        self.assertContains(resposta, "Escreva o nome do sistema próprio.")
        self.assertEqual(Campanha.objects.count(), 0)

    def test_nome_digitado_e_ignorado_com_sistema_da_lista(self):
        self.client.post(
            "/campanhas/nova/", dados_do_formulario(sistema_proprio="Qualquer coisa")
        )
        self.assertEqual(Campanha.objects.get().sistema_rpg, "D&D 5e")

    def test_editar_mostra_o_nome_do_sistema_proprio(self):
        campanha = self.criar_campanha(self.mestre, sistema_rpg="Reinos de Ferro")
        resposta = self.client.get(f"/campanhas/{campanha.id}/editar/")
        self.assertContains(resposta, '<option value="Sistema Próprio" selected>')
        self.assertContains(resposta, 'value="Reinos de Ferro"')

    def test_campanha_antiga_com_outro_pede_o_nome_ao_editar(self):
        campanha = self.criar_campanha(self.mestre, sistema_rpg="Outro")
        resposta = self.client.get(f"/campanhas/{campanha.id}/editar/")
        self.assertContains(resposta, '<option value="Sistema Próprio" selected>')

    def test_filtro_sistema_proprio_lista_os_nomes_digitados(self):
        self.criar_campanha(self.mestre, titulo="Mesa caseira", sistema_rpg="Reinos de Ferro")
        self.criar_campanha(self.mestre, titulo="Mesa antiga", sistema_rpg="Outro")
        self.criar_campanha(self.mestre, titulo="Mesa de D&D")
        resposta = self.client.get("/campanhas/", {"sistema": "Sistema Próprio"})
        self.assertContains(resposta, "Mesa caseira")
        self.assertContains(resposta, "Mesa antiga")
        self.assertNotContains(resposta, "Mesa de D&amp;D")


class MinhasCampanhasTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.outro = self.criar_usuario("outro")

    def test_exige_login(self):
        resposta = self.client.get("/campanhas/minhas/")
        self.assertEqual(resposta.status_code, 302)

    def test_mostra_so_as_campanhas_que_a_pessoa_criou(self):
        self.criar_campanha(self.mestre, titulo="Minha mesa")
        self.criar_campanha(self.mestre, titulo="Mesa que acabou", status="encerrada")
        self.criar_campanha(self.outro, titulo="Mesa de outra pessoa")
        self.entrar(self.mestre)
        resposta = self.client.get("/campanhas/minhas/")
        self.assertContains(resposta, "Minha mesa")
        self.assertContains(resposta, "Mesa que acabou")
        self.assertContains(resposta, "Encerradas")
        self.assertContains(resposta, "Você é mestre de 2 campanhas.")
        self.assertNotContains(resposta, "Mesa de outra pessoa")

    def test_link_no_menu(self):
        self.entrar(self.mestre)
        self.assertContains(self.client.get("/"), 'href="/campanhas/minhas/"')


class MarcacaoDasCampanhasTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.jogadora = self.criar_usuario("jogadora")
        self.inscrita = self.criar_campanha(
            self.mestre, titulo="Mesa com vaga",
            jogadores_inscritos_emails=[self.jogadora.email],
        )
        self.criar_campanha(self.mestre, titulo="Mesa sem ela")

    def test_lista_marca_a_campanha_em_que_a_pessoa_esta_inscrita(self):
        self.entrar(self.jogadora)
        resposta = self.client.get("/campanhas/")
        self.assertContains(resposta, "✓ Você está inscrito", count=1)
        self.assertContains(resposta, "ficha--jogador", count=1)

    def test_lista_marca_as_campanhas_do_mestre(self):
        self.entrar(self.mestre)
        resposta = self.client.get("/campanhas/")
        self.assertContains(resposta, "Você é o mestre", count=2)

    def test_sem_login_nada_e_marcado(self):
        resposta = self.client.get("/campanhas/")
        self.assertNotContains(resposta, "tag--papel")


class SinoDeNotificacoesTests(MongoTestCase):
    def test_sino_mostra_o_numero_de_nao_lidas(self):
        usuario = self.criar_usuario("ana")
        for texto in ("Aviso 1", "Aviso 2"):
            Notificacao(destinatario_email=usuario.email, texto=texto).save()
        self.entrar(usuario)
        resposta = self.client.get("/")
        self.assertContains(resposta, 'class="sino"')
        self.assertContains(resposta, 'aria-label="Notificações: 2 não lidas"')
        self.assertNotContains(resposta, ">Notificações<")
