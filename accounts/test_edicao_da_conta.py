"""RF01 - editar a conta: biografia, nome de usuário e e-mail.

Nome e e-mail são copiados em várias coleções (campanhas, comentários, chat,
avaliações, avisos...); estes testes conferem que as cópias acompanham a troca.
"""

import datetime
import re
from unittest import mock

from django.core import mail
from django.test import Client
from mongoengine.errors import NotUniqueError

from campanhas.models import Avaliacao, Campanha
from chat.models import MensagemChat
from core.base_testes import SENHA_PADRAO, MongoTestCase
from moderacao.models import ConteudoBloqueado
from notificacoes.models import Notificacao

from .identidade import trocar_email, trocar_username
from .models import Usuario


def _avaliar(campanha, de, para, nota=5, papel="mestre"):
    Avaliacao(
        campanha_id=str(campanha.id),
        campanha_titulo=campanha.titulo,
        avaliador_email=de.email,
        avaliador_username=de.username,
        avaliado_email=para.email,
        avaliado_username=para.username,
        papel_avaliado=papel,
        nota=nota,
    ).save()


class BaseEdicao(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.criar_usuario("ana")
        self.mestre = self.criar_usuario("mestre")
        self.joao = self.criar_usuario("joao")
        self.entrar(self.ana)

    def montar_a_vida_da_ana(self):
        """A Ana mestra uma mesa, joga na do mestre, comenta, fala no chat, avalia
        e é avaliada, e tem avisos e um texto barrado pela moderação."""
        self.mesa_da_ana = self.criar_campanha(
            self.ana, titulo="Mesa da Ana", jogadores_inscritos_emails=[self.joao.email]
        )
        self.mesa_da_ana.adicionar_comentario(self.ana.email, "ana", "Bem-vindos à minha mesa")
        self.mesa_da_ana.adicionar_comentario(self.joao.email, "joao", "Animado!")

        self.mesa_do_mestre = self.criar_campanha(
            self.mestre,
            titulo="Mesa do Mestre",
            max_jogadores=3,
            jogadores_inscritos_emails=[self.ana.email, self.joao.email],
        )
        self.mesa_do_mestre.adicionar_comentario(self.ana.email, "ana", "Posso levar um bardo?")
        self.mesa_do_mestre.adicionar_comentario(self.mestre.email, "mestre", "Pode!")

        for autor in (self.ana, self.mestre):
            MensagemChat.objects.create(
                campanha_id=str(self.mesa_do_mestre.id),
                autor_email=autor.email,
                autor_username=autor.username,
                texto=f"oi, sou {autor.username}",
            )

        _avaliar(self.mesa_do_mestre, de=self.ana, para=self.mestre)
        _avaliar(self.mesa_do_mestre, de=self.mestre, para=self.ana, papel="jogador")
        _avaliar(self.mesa_do_mestre, de=self.joao, para=self.ana, nota=4, papel="jogador")

        Notificacao.objects.create(
            destinatario_email=self.ana.email,
            texto="mestre avaliou você na campanha",
            url="/contas/u/ana/",
        )
        Notificacao.objects.create(
            destinatario_email=self.ana.email,
            texto="Mesa nova",
            url=f"/campanhas/{self.mesa_do_mestre.id}/",
        )
        ConteudoBloqueado.objects.create(
            autor_email=self.ana.email, texto_original="x", motivo="m", origem="chat:1"
        )

    def conferir_as_copias(self, email, username):
        """Tudo o que era da Ana carrega o e-mail e o nome dados; o resto não mudou."""
        mesa_da_ana = Campanha.objects.get(id=self.mesa_da_ana.id)
        mesa_do_mestre = Campanha.objects.get(id=self.mesa_do_mestre.id)

        self.assertEqual((mesa_da_ana.mestre_email, mesa_da_ana.mestre_username), (email, username))
        self.assertEqual(sorted(mesa_do_mestre.jogadores_inscritos_emails), sorted([email, self.joao.email]))
        self.assertEqual(mesa_do_mestre.vagas_livres, 1)

        comentarios = {c.texto: c for c in [*mesa_da_ana.comentarios, *mesa_do_mestre.comentarios]}
        for texto in ("Bem-vindos à minha mesa", "Posso levar um bardo?"):
            self.assertEqual(
                (comentarios[texto].autor_email, comentarios[texto].autor_username), (email, username)
            )
        # O que os outros escreveram não muda.
        self.assertEqual(comentarios["Animado!"].autor_username, "joao")
        self.assertEqual(comentarios["Pode!"].autor_email, self.mestre.email)

        mensagem_da_ana = [m for m in MensagemChat.objects if m.texto.startswith("oi, sou ana")][0]
        self.assertEqual((mensagem_da_ana.autor_email, mensagem_da_ana.autor_username), (email, username))
        mensagem_do_mestre = [m for m in MensagemChat.objects if m.texto == "oi, sou mestre"][0]
        self.assertEqual(mensagem_do_mestre.autor_email, self.mestre.email)

        escrita = Avaliacao.objects.get(avaliado_email=self.mestre.email)
        self.assertEqual((escrita.avaliador_email, escrita.avaliador_username), (email, username))
        recebidas = Avaliacao.objects(avaliado_email=email)
        self.assertEqual(sorted(a.avaliado_username for a in recebidas), [username, username])
        self.assertEqual(Avaliacao.objects(avaliador_email=self.joao.email).first().avaliado_email, email)

        self.assertEqual(Notificacao.objects(destinatario_email=email).count(), 2)
        self.assertEqual(ConteudoBloqueado.objects(autor_email=email).count(), 1)


# --------------------------------------------------------------------------
# Biografia
# --------------------------------------------------------------------------


class BiografiaTests(BaseEdicao):
    def salvar(self, bio, **extras):
        dados = {"avatar": "iniciais", "bio": bio}
        dados.update(extras)
        return self.client.post("/contas/perfil/", dados)

    def mensagens(self, resposta):
        return [str(m) for m in resposta.wsgi_request._messages]

    def test_a_pagina_oferece_o_campo_com_a_biografia_atual(self):
        self.ana.bio = "Mestre de terror cósmico."
        self.ana.save()
        resposta = self.client.get("/contas/perfil/")
        self.assertContains(resposta, 'name="bio"')
        self.assertContains(resposta, "Mestre de terror cósmico.")

    def test_salva_a_biografia_e_mostra_no_perfil_publico(self):
        resposta = self.salvar("Jogo desde 2009.\nAdoro investigação.")
        self.assertRedirects(resposta, "/contas/perfil/", fetch_redirect_response=False)
        self.ana.reload()
        self.assertEqual(self.ana.bio, "Jogo desde 2009.\nAdoro investigação.")

        publico = Client().get("/contas/u/ana/")
        self.assertContains(publico, "Jogo desde 2009.")
        self.assertContains(publico, "Adoro investigação.")

    def test_perfil_sem_biografia_nao_mostra_o_bloco(self):
        self.assertNotContains(Client().get("/contas/u/ana/"), "perfil-publico__bio")

    def test_limpar_a_biografia(self):
        self.salvar("Algo")
        self.salvar("")
        self.ana.reload()
        self.assertEqual(self.ana.bio, "")

    def test_o_limite_e_de_500_caracteres(self):
        self.assertContains(self.salvar("a" * 501), "no máximo 500 caracteres")
        self.ana.reload()
        self.assertEqual(self.ana.bio, "")
        self.salvar("a" * 500)
        self.ana.reload()
        self.assertEqual(len(self.ana.bio), 500)

    def test_quebras_de_linha_do_navegador_contam_como_um_caractere(self):
        # 300 letras e 150 quebras: 450 no navegador, mas 600 se \r\n valesse dois.
        texto_do_navegador = "a\r\n" * 150 + "a" * 150
        self.salvar(texto_do_navegador)
        self.ana.reload()
        self.assertEqual(self.ana.bio, "a\n" * 150 + "a" * 150)

    def test_html_na_biografia_aparece_como_texto(self):
        self.salvar("<script>alert(1)</script> olá")
        publico = Client().get("/contas/u/ana/")
        self.assertNotContains(publico, "<script>alert(1)</script>")
        self.assertContains(publico, "&lt;script&gt;alert(1)&lt;/script&gt; olá")

    def test_a_moderacao_barra_a_biografia_ofensiva(self):
        resposta = self.salvar("você é um idiota", avatar="iniciais")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "campo__erro")
        self.ana.reload()
        self.assertEqual(self.ana.bio, "")
        bloqueio = ConteudoBloqueado.objects.get()
        self.assertEqual(bloqueio.origem, "perfil:bio")
        self.assertEqual(bloqueio.autor_email, self.ana.email)

    def test_biografia_barrada_nao_salva_nem_o_avatar(self):
        self.client.post("/contas/perfil/", {"avatar": "iniciais", "bio": "ok"})
        versao = Usuario.objects.get(id=self.ana.id).avatar_versao
        self.salvar("você é um idiota")
        self.assertEqual(Usuario.objects.get(id=self.ana.id).avatar_versao, versao)

    def test_biografia_que_nao_mudou_nao_e_moderada_de_novo(self):
        # Texto gravado antes (por outro caminho) que o filtro de hoje barraria.
        self.ana.bio = "você é um idiota"
        self.ana.save()
        resposta = self.salvar("você é um idiota")
        self.assertRedirects(resposta, "/contas/perfil/", fetch_redirect_response=False)
        self.assertEqual(ConteudoBloqueado.objects.count(), 0)

    def test_aparece_na_exportacao_dos_dados(self):
        self.salvar("Minha história")
        resposta = self.client.post("/contas/exportar/")
        self.assertContains(resposta, "Minha história")

    def test_o_link_do_proprio_perfil_leva_a_edicao(self):
        self.assertContains(self.client.get("/contas/u/ana/"), "Editar meu perfil")
        self.assertNotContains(Client().get("/contas/u/ana/"), "Editar meu perfil")


# --------------------------------------------------------------------------
# Nome de usuário
# --------------------------------------------------------------------------


class NomeDeUsuarioTests(BaseEdicao):
    def trocar(self, novo, **extras):
        dados = {"acao": "usuario", "usuario-novo_username": novo}
        dados.update(extras)
        return self.client.post("/contas/conta/", dados)

    def mensagens(self, resposta):
        return [str(m) for m in resposta.wsgi_request._messages]

    def test_a_pagina_tem_o_formulario(self):
        resposta = self.client.get("/contas/conta/")
        self.assertContains(resposta, 'name="usuario-novo_username"')
        self.assertContains(resposta, 'value="usuario"')

    def test_troca_o_nome(self):
        resposta = self.trocar("ana_nova")
        self.assertRedirects(resposta, "/contas/conta/", fetch_redirect_response=False)
        self.assertIn("Nome de usuário alterado para ana_nova.", self.mensagens(resposta))
        self.ana.reload()
        self.assertEqual(self.ana.username, "ana_nova")
        self.assertEqual(self.ana.email, "ana@exemplo.com")

    def test_as_copias_do_nome_acompanham(self):
        self.montar_a_vida_da_ana()
        self.trocar("ana_nova")
        self.conferir_as_copias("ana@exemplo.com", "ana_nova")

    def test_o_aviso_que_levava_ao_perfil_antigo_passa_a_levar_ao_novo(self):
        self.montar_a_vida_da_ana()
        self.trocar("ana_nova")
        urls = sorted(n.url for n in Notificacao.objects(destinatario_email=self.ana.email))
        self.assertEqual(urls, sorted(["/contas/u/ana_nova/", f"/campanhas/{self.mesa_do_mestre.id}/"]))

    def test_o_perfil_antigo_some_e_o_novo_responde(self):
        self.trocar("ana_nova")
        self.assertEqual(Client().get("/contas/u/ana/").status_code, 404)
        self.assertEqual(Client().get("/contas/u/ana_nova/").status_code, 200)

    def test_a_sessao_continua_valida_depois_da_troca(self):
        self.trocar("ana_nova")
        self.assertContains(self.client.get("/contas/conta/"), "ana_nova")
        self.assertEqual(self.client.get("/campanhas/minhas/").status_code, 200)

    def test_nome_de_outra_conta_e_recusado(self):
        resposta = self.trocar("mestre")
        self.assertContains(resposta, "Esse nome de usuário já está em uso.")
        self.ana.reload()
        self.assertEqual(self.ana.username, "ana")

    def test_o_mesmo_nome_e_recusado(self):
        self.assertContains(self.trocar("ana"), "Esse já é o seu nome de usuário.")

    def test_tamanho_minimo_e_maximo(self):
        self.assertEqual(self.trocar("ab").status_code, 200)
        self.assertEqual(self.trocar("a" * 31).status_code, 200)
        self.ana.reload()
        self.assertEqual(self.ana.username, "ana")
        self.trocar("a" * 30)
        self.ana.reload()
        self.assertEqual(self.ana.username, "a" * 30)

    def test_espacos_nas_pontas_sao_aparados(self):
        self.trocar("   ana_nova  ")
        self.ana.reload()
        self.assertEqual(self.ana.username, "ana_nova")

    def test_pode_mudar_so_a_caixa_das_letras(self):
        self.trocar("Ana")
        self.ana.reload()
        self.assertEqual(self.ana.username, "Ana")

    def test_conta_antiga_nao_confirmada_nao_vira_um_nome_duplicado(self):
        # Conta de antes da confirmação por e-mail: o formulário (como o cadastro)
        # não a conta, mas o índice único do banco recusa e vira um erro na tela.
        self.criar_usuario("fantasma", aguardando_confirmacao=True)
        resposta = self.trocar("fantasma")
        self.assertContains(resposta, "Esse nome de usuário já está em uso.")
        self.ana.reload()
        self.assertEqual(self.ana.username, "ana")
        self.assertEqual(Usuario.objects(username="fantasma").count(), 1)

    def test_corrida_pelo_mesmo_nome_vira_erro_no_formulario(self):
        with mock.patch("accounts.views.trocar_username", side_effect=NotUniqueError("dup")):
            resposta = self.trocar("ana_nova")
        self.assertContains(resposta, "Esse nome de usuário já está em uso.")
        self.assertContains(resposta, ">ana<")  # a página volta com o nome de antes
        self.ana.reload()
        self.assertEqual(self.ana.username, "ana")

    def test_as_outras_pessoas_nao_sao_tocadas(self):
        self.montar_a_vida_da_ana()
        self.trocar("ana_nova")
        self.assertEqual(Usuario.objects.get(id=self.mestre.id).username, "mestre")
        self.assertEqual(Campanha.objects.get(id=self.mesa_do_mestre.id).mestre_username, "mestre")

    def test_exige_login(self):
        resposta = Client().post("/contas/conta/", {"acao": "usuario", "usuario-novo_username": "x" * 5})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("login", resposta.url)

    def test_a_troca_de_senha_continua_funcionando_com_os_tres_formularios(self):
        resposta = self.client.post(
            "/contas/conta/",
            {
                "acao": "senha",
                "senha_atual": SENHA_PADRAO,
                "nova_senha": "Outra-senha-forte-456",
                "confirmar_nova_senha": "Outra-senha-forte-456",
            },
        )
        self.assertRedirects(resposta, "/contas/conta/", fetch_redirect_response=False)
        self.ana.reload()
        self.assertTrue(self.ana.checar_senha("Outra-senha-forte-456"))

    def test_a_funcao_acerta_as_copias_sem_passar_pela_tela(self):
        self.montar_a_vida_da_ana()
        trocar_username(self.ana, "ana_nova")
        self.conferir_as_copias("ana@exemplo.com", "ana_nova")


# --------------------------------------------------------------------------
# E-mail
# --------------------------------------------------------------------------

NOVO = "ana.nova@exemplo.com"


class EmailTests(BaseEdicao):
    def pedir(self, novo=NOVO, senha=SENHA_PADRAO, **extras):
        dados = {"acao": "email", "email-novo_email": novo, "email-senha_atual": senha}
        dados.update(extras)
        return self.client.post("/contas/conta/", dados)

    def mensagens(self, resposta):
        return [str(m) for m in resposta.wsgi_request._messages]

    def token_do_email(self):
        corpo = mail.outbox[-1].body
        return re.search(r"/contas/confirmar-novo-email/([^/\s]+)/", corpo).group(1)

    def confirmar(self, token=None, cliente=None):
        cliente = cliente or Client()
        return cliente.get(f"/contas/confirmar-novo-email/{token or self.token_do_email()}/")

    # -- o pedido -----------------------------------------------------------

    def test_a_pagina_tem_o_formulario(self):
        resposta = self.client.get("/contas/conta/")
        self.assertContains(resposta, 'name="email-novo_email"')
        self.assertContains(resposta, 'name="email-senha_atual"')

    def test_o_pedido_manda_o_link_para_o_endereco_novo_e_ainda_nao_troca(self):
        resposta = self.pedir()
        self.assertRedirects(resposta, "/contas/conta/", fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [NOVO])
        self.assertIn("http://127.0.0.1:8000/contas/confirmar-novo-email/", mail.outbox[0].body)

        self.ana.reload()
        self.assertEqual(self.ana.email, "ana@exemplo.com")
        self.assertEqual(self.ana.novo_email, NOVO)
        self.assertTrue(self.ana.token_novo_email)
        self.assertGreater(self.ana.token_novo_email_expira_em, datetime.datetime.utcnow())

    def test_a_pagina_avisa_do_pedido_pendente(self):
        self.pedir()
        resposta = self.client.get("/contas/conta/")
        self.assertContains(resposta, "Aguardando confirmação")
        self.assertContains(resposta, NOVO)

    def test_sem_pedido_a_pagina_nao_fala_em_confirmacao_pendente(self):
        self.assertNotContains(self.client.get("/contas/conta/"), "Aguardando confirmação")

    def test_o_endereco_e_guardado_em_minusculas(self):
        self.pedir("Ana.Nova@Exemplo.COM")
        self.ana.reload()
        self.assertEqual(self.ana.novo_email, NOVO)
        self.assertEqual(mail.outbox[0].to, [NOVO])

    def test_senha_errada_nao_envia_nada(self):
        resposta = self.pedir(senha="errada-errada")
        self.assertContains(resposta, "A senha atual não confere.")
        self.assertEqual(len(mail.outbox), 0)
        self.ana.reload()
        self.assertIsNone(self.ana.novo_email)

    def test_email_de_outra_conta_e_recusado(self):
        resposta = self.pedir("mestre@exemplo.com")
        self.assertContains(resposta, "Já existe uma conta com esse e-mail.")
        self.assertEqual(len(mail.outbox), 0)

    def test_o_mesmo_email_e_recusado(self):
        self.assertContains(self.pedir("ana@exemplo.com"), "Esse já é o e-mail da sua conta.")

    def test_endereco_invalido_e_recusado(self):
        self.assertEqual(self.pedir("isso-nao-e-email").status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_falha_no_envio_nao_grava_o_pedido(self):
        with mock.patch("accounts.views.send_mail", side_effect=OSError("smtp fora do ar")):
            with self.assertLogs("accounts.views", level="ERROR"):
                resposta = self.pedir()
        self.assertContains(resposta, "Não conseguimos enviar o e-mail de confirmação")
        self.ana.reload()
        self.assertIsNone(self.ana.novo_email)
        self.assertIsNone(self.ana.token_novo_email)

    def test_pedidos_em_sequencia_esperam_um_minuto(self):
        self.pedir()
        resposta = self.pedir("outra@exemplo.com")
        self.assertContains(resposta, "Aguarde")
        self.assertEqual(len(mail.outbox), 1)
        self.ana.reload()
        self.assertEqual(self.ana.novo_email, NOVO)

    def test_um_pedido_novo_substitui_o_anterior(self):
        self.pedir()
        primeiro = self.token_do_email()
        # Como se o primeiro pedido tivesse sido feito há mais de um minuto.
        self.ana.reload()
        self.ana.token_novo_email_expira_em -= datetime.timedelta(minutes=5)
        self.ana.save()

        self.pedir("outra@exemplo.com")
        self.assertEqual(len(mail.outbox), 2)
        self.ana.reload()
        self.assertEqual(self.ana.novo_email, "outra@exemplo.com")

        self.confirmar(primeiro)  # o link antigo não vale mais
        self.ana.reload()
        self.assertEqual(self.ana.email, "ana@exemplo.com")

    def test_exige_login_para_pedir(self):
        resposta = Client().post("/contas/conta/", {"acao": "email"})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("login", resposta.url)

    # -- a confirmação ------------------------------------------------------

    def test_confirmar_troca_o_email_da_conta(self):
        self.pedir()
        resposta = self.confirmar(cliente=self.client)
        self.assertRedirects(resposta, "/contas/conta/", fetch_redirect_response=False)
        self.assertTrue(any("E-mail alterado para" in m for m in self.mensagens(resposta)))
        self.ana.reload()
        self.assertEqual(self.ana.email, NOVO)
        self.assertIsNone(self.ana.novo_email)
        self.assertIsNone(self.ana.token_novo_email)
        self.assertIsNone(self.ana.token_novo_email_expira_em)

    def test_confirmar_nao_exige_estar_logado_no_navegador_do_link(self):
        self.pedir()
        self.confirmar(cliente=Client())
        self.ana.reload()
        self.assertEqual(self.ana.email, NOVO)

    def test_as_copias_do_email_acompanham(self):
        self.montar_a_vida_da_ana()
        self.pedir()
        self.confirmar()
        self.conferir_as_copias(NOVO, "ana")

    def test_depois_da_troca_o_login_e_pelo_email_novo(self):
        self.pedir()
        self.confirmar()
        antigo = Client().post("/contas/login/", {"email": "ana@exemplo.com", "senha": SENHA_PADRAO})
        self.assertEqual(antigo.status_code, 200)
        self.assertContains(antigo, "E-mail ou senha inválidos.")
        novo = Client().post("/contas/login/", {"email": NOVO, "senha": SENHA_PADRAO})
        self.assertRedirects(novo, "/", fetch_redirect_response=False)

    def test_a_pessoa_continua_dona_das_mesas_e_inscricoes(self):
        self.montar_a_vida_da_ana()
        self.pedir()
        self.confirmar()
        self.assertEqual(self.client.get("/campanhas/minhas/").context["total"], 1)
        self.assertEqual(self.client.get("/campanhas/inscricoes/").context["total"], 1)
        self.assertEqual(self.client.get(f"/chat/{self.mesa_do_mestre.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/chat/{self.mesa_da_ana.id}/").status_code, 200)

    def test_o_sininho_mostra_os_avisos_de_antes(self):
        self.montar_a_vida_da_ana()
        self.pedir()
        self.confirmar()
        self.assertEqual(self.client.get("/notificacoes/").context["notificacoes"].count(), 2)

    def test_a_exportacao_mostra_o_email_aguardando_confirmacao(self):
        self.assertIsNone(self.client.post("/contas/exportar/").json()["conta"]["email_aguardando_confirmacao"])
        self.pedir()
        conta = self.client.post("/contas/exportar/").json()["conta"]
        self.assertEqual(conta["email"], "ana@exemplo.com")
        self.assertEqual(conta["email_aguardando_confirmacao"], NOVO)
        self.confirmar()
        conta = self.client.post("/contas/exportar/").json()["conta"]
        self.assertEqual(conta["email"], NOVO)
        self.assertIsNone(conta["email_aguardando_confirmacao"])

    def test_a_exportacao_traz_o_email_novo(self):
        self.pedir()
        self.confirmar()
        self.assertContains(self.client.post("/contas/exportar/"), NOVO)

    def test_o_link_so_vale_uma_vez(self):
        self.pedir()
        token = self.token_do_email()
        self.confirmar(token)
        resposta = self.confirmar(token)
        self.assertEqual(resposta.status_code, 302)
        self.ana.reload()
        self.assertEqual(self.ana.email, NOVO)

    def test_link_invalido_nao_faz_nada(self):
        self.pedir()
        resposta = self.confirmar("token-que-nao-existe")
        self.assertEqual(resposta.status_code, 302)
        self.ana.reload()
        self.assertEqual(self.ana.email, "ana@exemplo.com")
        self.assertEqual(self.ana.novo_email, NOVO)

    def test_link_expirado_nao_vale(self):
        self.pedir()
        token = self.token_do_email()
        self.ana.reload()
        self.ana.token_novo_email_expira_em = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
        self.ana.save()
        self.confirmar(token)
        self.ana.reload()
        self.assertEqual(self.ana.email, "ana@exemplo.com")
        # E a página não finge que o pedido ainda está de pé.
        self.assertNotContains(self.client.get("/contas/conta/"), "Aguardando confirmação")

    def test_o_endereco_foi_tomado_enquanto_o_link_esperava(self):
        self.pedir()
        token = self.token_do_email()
        self.criar_usuario("intruso", email=NOVO)
        resposta = self.confirmar(token, cliente=self.client)
        self.assertRedirects(resposta, "/contas/conta/", fetch_redirect_response=False)
        self.assertTrue(
            any("passou a ser usado por outra conta" in m for m in self.mensagens(resposta))
        )
        self.ana.reload()
        self.assertEqual(self.ana.email, "ana@exemplo.com")
        self.assertIsNone(self.ana.novo_email)

    def test_confirmar_invalida_link_de_recuperacao_de_senha_pendente(self):
        self.ana.token_recuperacao_senha = "recuperar"
        self.ana.token_recuperacao_expira_em = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        self.ana.save()
        self.pedir()
        self.confirmar()
        self.ana.reload()
        self.assertIsNone(self.ana.token_recuperacao_senha)
        self.assertEqual(Client().get("/contas/redefinir-senha/recuperar/").status_code, 302)

    def test_refazer_a_troca_depois_de_uma_falha_no_meio_da_mesmo_resultado(self):
        """A troca atualiza as cópias antes da conta e cada passo pode ser refeito:
        se algo parar no meio, clicar de novo no link conclui o serviço."""
        self.montar_a_vida_da_ana()
        # A falha aconteceu logo depois de a inscrição ganhar o endereço novo.
        Campanha.objects(id=self.mesa_do_mestre.id).update(
            add_to_set__jogadores_inscritos_emails=NOVO
        )
        trocar_email(self.ana, NOVO)
        self.conferir_as_copias(NOVO, "ana")

        # E rodar tudo outra vez não muda nada.
        self.ana.email = "ana@exemplo.com"
        trocar_email(self.ana, NOVO)
        self.conferir_as_copias(NOVO, "ana")

    def test_troca_de_email_e_de_nome_juntas(self):
        self.montar_a_vida_da_ana()
        self.pedir()
        self.confirmar()
        self.client.post("/contas/conta/", {"acao": "usuario", "usuario-novo_username": "ana_nova"})
        self.conferir_as_copias(NOVO, "ana_nova")
