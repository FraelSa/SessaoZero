"""RNF02 / RNF03 - segurança das contas: senhas, links de e-mail, tentativas e sessões."""

import datetime
import hashlib
from unittest import mock

from django.conf import settings
from django.contrib.auth.hashers import PBKDF2PasswordHasher, check_password
from django.core import mail
from django.test import Client, SimpleTestCase

from core.base_testes import SENHA_PADRAO, MongoTestCase
from core.privacidade import mascarar_email

from .models import CadastroPendente, TentativaLogin, Usuario
from .tokens import gerar_token, resumo_do_token

NOVA_SENHA = "Outra-senha-forte-456"
EMAIL_ANA = "ana@exemplo.com"


def minutos_atras(minutos):
    return datetime.datetime.utcnow() - datetime.timedelta(minutes=minutos)


# --------------------------------------------------------------------------
# Códigos dos links de e-mail
# --------------------------------------------------------------------------


class TokensTests(SimpleTestCase):
    def test_o_resumo_nao_e_o_token_e_e_sempre_o_mesmo(self):
        self.assertNotEqual(resumo_do_token("abc"), "abc")
        self.assertEqual(resumo_do_token("abc"), resumo_do_token("abc"))
        self.assertEqual(resumo_do_token("abc"), hashlib.sha256(b"abc").hexdigest())

    def test_gerar_token_devolve_o_token_e_o_resumo_dele(self):
        token, resumo = gerar_token()
        self.assertEqual(resumo, resumo_do_token(token))
        self.assertNotEqual(token, resumo)
        self.assertGreaterEqual(len(token), 43)  # 256 bits em base64

    def test_cada_token_e_diferente(self):
        self.assertEqual(len({gerar_token()[0] for _ in range(50)}), 50)


class LinkDeConfirmacaoTests(MongoTestCase):
    def cadastrar(self):
        return Client().post(
            "/contas/cadastro/",
            {
                "username": "novata",
                "email": "novata@exemplo.com",
                "senha": SENHA_PADRAO,
                "confirmar_senha": SENHA_PADRAO,
                "aceite_politica": "on",
            },
        )

    def test_o_banco_guarda_so_o_resumo_do_codigo_que_vai_no_email(self):
        self.cadastrar()
        token = self.token_do_email("confirmar-email")
        pendente = CadastroPendente.objects.get()
        self.assertNotEqual(pendente.token, token)
        self.assertEqual(pendente.token, resumo_do_token(token))

    def test_o_codigo_do_email_confirma_o_cadastro(self):
        self.cadastrar()
        Client().get(f"/contas/confirmar-email/{self.token_do_email('confirmar-email')}/")
        self.assertEqual(Usuario.objects.get().email, "novata@exemplo.com")
        self.assertEqual(CadastroPendente.objects.count(), 0)

    def test_o_resumo_que_esta_no_banco_nao_abre_o_link(self):
        """Quem lesse o banco não conseguiria confirmar cadastros alheios."""
        self.cadastrar()
        resumo = CadastroPendente.objects.get().token
        Client().get(f"/contas/confirmar-email/{resumo}/")
        self.assertEqual(Usuario.objects.count(), 0)
        self.assertEqual(CadastroPendente.objects.count(), 1)

    def test_reenviar_troca_o_codigo_e_o_antigo_deixa_de_valer(self):
        self.cadastrar()
        primeiro = self.token_do_email("confirmar-email")
        CadastroPendente.objects.update(set__ultimo_envio_em=minutos_atras(5))

        Client().post("/contas/reenviar-confirmacao/", {"email": "novata@exemplo.com"})
        self.assertEqual(len(mail.outbox), 2)
        segundo = self.token_do_email("confirmar-email")
        self.assertNotEqual(primeiro, segundo)

        Client().get(f"/contas/confirmar-email/{primeiro}/")
        self.assertEqual(Usuario.objects.count(), 0)
        Client().get(f"/contas/confirmar-email/{segundo}/")
        self.assertEqual(Usuario.objects.count(), 1)


class LinkDeTrocaDeEmailTests(MongoTestCase):
    def test_o_banco_guarda_so_o_resumo_do_codigo_que_vai_no_email(self):
        ana = self.criar_usuario("ana")
        self.entrar(ana)
        self.client.post(
            "/contas/conta/",
            {
                "acao": "email",
                "email-novo_email": "ana.nova@exemplo.com",
                "email-senha_atual": SENHA_PADRAO,
            },
        )
        token = self.token_do_email("confirmar-novo-email")
        ana.reload()
        self.assertNotEqual(ana.token_novo_email, token)
        self.assertEqual(ana.token_novo_email, resumo_do_token(token))

        # O resumo guardado não abre o link; o código do e-mail, sim.
        Client().get(f"/contas/confirmar-novo-email/{ana.token_novo_email}/")
        ana.reload()
        self.assertEqual(ana.email, EMAIL_ANA)
        Client().get(f"/contas/confirmar-novo-email/{token}/")
        ana.reload()
        self.assertEqual(ana.email, "ana.nova@exemplo.com")


class RecuperacaoDeSenhaTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.criar_usuario("ana")

    def pedir(self, email=EMAIL_ANA):
        return Client().post("/contas/recuperar-senha/", {"email": email})

    def redefinir(self, token, senha=NOVA_SENHA, cliente=None):
        return (cliente or Client()).post(
            f"/contas/redefinir-senha/{token}/",
            {"nova_senha": senha, "confirmar_nova_senha": senha},
        )

    def mensagens(self, resposta):
        return [str(m) for m in resposta.wsgi_request._messages]

    def test_o_banco_guarda_so_o_resumo_do_codigo_que_vai_no_email(self):
        self.pedir()
        token = self.token_do_email("redefinir-senha")
        self.ana.reload()
        self.assertNotEqual(self.ana.token_recuperacao_senha, token)
        self.assertEqual(self.ana.token_recuperacao_senha, resumo_do_token(token))

    def test_o_link_do_email_redefine_a_senha(self):
        self.pedir()
        resposta = self.redefinir(self.token_do_email("redefinir-senha"))
        self.assertRedirects(resposta, "/contas/login/", fetch_redirect_response=False)
        self.ana.reload()
        self.assertTrue(self.ana.checar_senha(NOVA_SENHA))
        self.assertFalse(self.ana.checar_senha(SENHA_PADRAO))
        self.assertIsNone(self.ana.token_recuperacao_senha)

    def test_o_link_so_vale_uma_vez(self):
        self.pedir()
        token = self.token_do_email("redefinir-senha")
        self.redefinir(token)
        self.redefinir(token, senha="Mais-uma-senha-789")
        self.ana.reload()
        self.assertTrue(self.ana.checar_senha(NOVA_SENHA))

    def test_o_resumo_que_esta_no_banco_nao_abre_o_link(self):
        self.pedir()
        self.ana.reload()
        resposta = Client().get(f"/contas/redefinir-senha/{self.ana.token_recuperacao_senha}/")
        self.assertRedirects(resposta, "/contas/recuperar-senha/", fetch_redirect_response=False)
        resposta = self.redefinir(self.ana.token_recuperacao_senha)
        self.ana.reload()
        self.assertTrue(self.ana.checar_senha(SENHA_PADRAO))

    def test_link_vencido_nao_vale(self):
        self.pedir()
        token = self.token_do_email("redefinir-senha")
        Usuario.objects.update(set__token_recuperacao_expira_em=minutos_atras(1))
        self.redefinir(token)
        self.ana.reload()
        self.assertTrue(self.ana.checar_senha(SENHA_PADRAO))

    def test_conta_que_nao_existe_recebe_a_mesma_resposta_e_nenhum_email(self):
        existe = self.pedir()
        nao_existe = self.pedir("ninguem@exemplo.com")
        self.assertEqual(self.mensagens(existe), self.mensagens(nao_existe))
        self.assertEqual(len(mail.outbox), 1)

    def test_pedidos_em_sequencia_mandam_um_so_email_e_o_link_segue_valendo(self):
        self.pedir()
        primeira_resposta = self.pedir()
        self.pedir()
        self.assertEqual(len(mail.outbox), 1)
        # A resposta continua igual, para não revelar que o pedido foi segurado.
        self.assertEqual(
            self.mensagens(primeira_resposta), self.mensagens(self.pedir("ninguem@exemplo.com"))
        )
        resposta = self.redefinir(self.token_do_email("redefinir-senha"))
        self.assertRedirects(resposta, "/contas/login/", fetch_redirect_response=False)

    def test_passado_o_intervalo_um_novo_pedido_manda_outro_link_e_o_antigo_morre(self):
        self.pedir()
        primeiro = self.token_do_email("redefinir-senha")
        self.ana.reload()
        self.ana.token_recuperacao_expira_em -= datetime.timedelta(minutes=2)
        self.ana.save()

        self.pedir()
        self.assertEqual(len(mail.outbox), 2)
        segundo = self.token_do_email("redefinir-senha")
        self.assertNotEqual(primeiro, segundo)
        self.assertEqual(Client().get(f"/contas/redefinir-senha/{primeiro}/").status_code, 302)
        self.assertEqual(Client().get(f"/contas/redefinir-senha/{segundo}/").status_code, 200)

    def test_falha_no_envio_nao_vira_erro_nao_grava_o_link_e_nao_mostra_o_email_no_log(self):
        with mock.patch("accounts.views.send_mail", side_effect=OSError("smtp fora do ar")):
            with self.assertLogs("accounts.views", level="ERROR") as registro:
                resposta = self.pedir()
        self.assertEqual(resposta.status_code, 302)
        self.ana.reload()
        self.assertIsNone(self.ana.token_recuperacao_senha)
        saida = "\n".join(registro.output)
        self.assertNotIn(EMAIL_ANA, saida)
        self.assertIn("a***@exemplo.com", saida)

    def test_a_resposta_e_a_mesma_quando_o_envio_falha(self):
        normal = self.pedir()
        Usuario.objects.update(unset__token_recuperacao_expira_em=True)
        with mock.patch("accounts.views.send_mail", side_effect=OSError("smtp fora do ar")):
            with self.assertLogs("accounts.views", level="ERROR"):
                falhou = self.pedir()
        self.assertEqual(self.mensagens(normal), self.mensagens(falhou))

    def test_redefinir_a_senha_encerra_as_sessoes_abertas(self):
        outro_aparelho = Client()
        outro_aparelho.post("/contas/login/", {"email": EMAIL_ANA, "senha": SENHA_PADRAO})
        self.assertEqual(outro_aparelho.get("/contas/conta/").status_code, 200)

        self.pedir()
        self.redefinir(self.token_do_email("redefinir-senha"))

        resposta = outro_aparelho.get("/contas/conta/")
        self.assertRedirects(resposta, "/contas/login/", fetch_redirect_response=False)

    def test_redefinir_a_senha_destrava_o_login(self):
        for _ in range(5):
            Client().post("/contas/login/", {"email": EMAIL_ANA, "senha": "senha-errada-1"})
        self.pedir()
        self.redefinir(self.token_do_email("redefinir-senha"))
        resposta = Client().post("/contas/login/", {"email": EMAIL_ANA, "senha": NOVA_SENHA})
        self.assertRedirects(resposta, "/", fetch_redirect_response=False)


# --------------------------------------------------------------------------
# Senhas
# --------------------------------------------------------------------------


class SenhaTests(MongoTestCase):
    def hash_antigo(self, usuario, iteracoes=1000):
        hasher = PBKDF2PasswordHasher()
        usuario.senha_hash = hasher.encode(SENHA_PADRAO, hasher.salt(), iterations=iteracoes)
        usuario.save()
        return hasher.iterations

    def test_senha_fica_com_hash_forte_e_com_sal(self):
        ana = self.criar_usuario("ana")
        bia = self.criar_usuario("bia")
        algoritmo, iteracoes = ana.senha_hash.split("$")[:2]
        self.assertEqual(algoritmo, "pbkdf2_sha256")
        self.assertGreaterEqual(int(iteracoes), 600_000)  # mínimo recomendado pela OWASP
        self.assertNotIn(SENHA_PADRAO, ana.senha_hash)
        self.assertNotEqual(ana.senha_hash, bia.senha_hash)  # mesmo texto, sal diferente

    def test_hash_mais_fraco_e_refeito_quando_a_pessoa_entra(self):
        ana = self.criar_usuario("ana")
        iteracoes_atuais = self.hash_antigo(ana)
        antigo = ana.senha_hash

        resposta = Client().post("/contas/login/", {"email": EMAIL_ANA, "senha": SENHA_PADRAO})
        self.assertEqual(resposta.status_code, 302)

        ana.reload()
        self.assertNotEqual(ana.senha_hash, antigo)
        self.assertEqual(int(ana.senha_hash.split("$")[1]), iteracoes_atuais)
        self.assertTrue(check_password(SENHA_PADRAO, ana.senha_hash))

    def test_senha_errada_nao_mexe_no_hash(self):
        ana = self.criar_usuario("ana")
        self.hash_antigo(ana)
        antigo = ana.senha_hash
        Client().post("/contas/login/", {"email": EMAIL_ANA, "senha": "senha-errada-1"})
        ana.reload()
        self.assertEqual(ana.senha_hash, antigo)

    def test_refazer_o_hash_nao_apaga_o_que_outra_requisicao_gravou(self):
        ana = self.criar_usuario("ana")
        self.hash_antigo(ana)
        lido_pela_view = Usuario.objects.get(id=ana.id)
        Usuario.objects(id=ana.id).update_one(set__bio="bio nova")  # grava depois da leitura

        self.assertTrue(lido_pela_view.checar_senha(SENHA_PADRAO))

        ana.reload()
        self.assertEqual(ana.bio, "bio nova")
        self.assertGreaterEqual(int(ana.senha_hash.split("$")[1]), 600_000)


class MascararEmailTests(SimpleTestCase):
    def test_mostra_so_a_primeira_letra_e_o_dominio(self):
        self.assertEqual(mascarar_email("ana.silva@exemplo.com"), "a***@exemplo.com")

    def test_sem_arroba_ou_vazio_nao_mostra_nada(self):
        for valor in ("estranho", "", None):
            self.assertEqual(mascarar_email(valor), "***")


# --------------------------------------------------------------------------
# Limite de tentativas de senha
# --------------------------------------------------------------------------


class LimiteDeLoginTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.criar_usuario("ana")

    def entrar_com(self, senha, email=EMAIL_ANA, cliente=None):
        return (cliente or Client()).post("/contas/login/", {"email": email, "senha": senha})

    def errar(self, vezes, email=EMAIL_ANA):
        for _ in range(vezes):
            self.assertContains(
                self.entrar_com("senha-errada-1", email), "E-mail ou senha inválidos."
            )

    def test_depois_de_cinco_senhas_erradas_ate_a_senha_certa_e_recusada(self):
        self.errar(5)
        cliente = Client()
        resposta = self.entrar_com(SENHA_PADRAO, cliente=cliente)
        self.assertContains(resposta, "Muitas tentativas")
        self.assertNotIn("usuario_id", cliente.session)

    def test_quatro_erros_ainda_nao_travam(self):
        self.errar(4)
        self.assertEqual(self.entrar_com(SENHA_PADRAO).status_code, 302)

    def test_travado_nem_calcula_o_hash_da_senha(self):
        self.errar(5)
        with mock.patch.object(Usuario, "checar_senha") as checar:
            self.entrar_com(SENHA_PADRAO)
        checar.assert_not_called()

    def test_a_mensagem_diz_quanto_esperar(self):
        self.errar(5)
        self.assertContains(self.entrar_com(SENHA_PADRAO), "aguarde 15 minutos")

    def test_a_espera_diminui_conforme_as_falhas_envelhecem(self):
        self.errar(5)
        TentativaLogin.objects.update(set__quando=minutos_atras(14))
        self.assertContains(self.entrar_com(SENHA_PADRAO), "aguarde 1 minuto ")

    def test_passada_a_janela_a_pessoa_volta_a_poder_entrar(self):
        self.errar(5)
        TentativaLogin.objects.update(set__quando=minutos_atras(16))
        self.assertEqual(self.entrar_com(SENHA_PADRAO).status_code, 302)

    def test_acertar_a_senha_zera_a_contagem(self):
        self.errar(4)
        self.assertEqual(self.entrar_com(SENHA_PADRAO).status_code, 302)
        self.assertEqual(TentativaLogin.objects.count(), 0)
        self.errar(4)
        self.assertEqual(self.entrar_com(SENHA_PADRAO).status_code, 302)

    def test_email_que_nao_existe_trava_do_mesmo_jeito(self):
        self.errar(5, email="ninguem@exemplo.com")
        resposta = self.entrar_com(SENHA_PADRAO, email="ninguem@exemplo.com")
        self.assertContains(resposta, "Muitas tentativas")

    def test_outro_email_nao_e_afetado(self):
        bia = self.criar_usuario("bia")
        self.errar(5)
        self.assertEqual(self.entrar_com(SENHA_PADRAO, email=bia.email).status_code, 302)

    def test_maiusculas_e_espacos_contam_como_o_mesmo_email(self):
        for _ in range(3):
            self.entrar_com("senha-errada-1", email="ANA@Exemplo.com")
        for _ in range(2):
            self.entrar_com("senha-errada-1", email=EMAIL_ANA)
        self.assertContains(self.entrar_com(SENHA_PADRAO), "Muitas tentativas")

    def test_o_registro_guarda_so_o_resumo_do_email(self):
        self.errar(1)
        registro = TentativaLogin.objects.get()
        self.assertEqual(registro.chave, hashlib.sha256(EMAIL_ANA.encode()).hexdigest())

    def test_os_registros_somem_sozinhos_do_banco(self):
        indices = TentativaLogin._get_collection().index_information()
        ttl = [info for info in indices.values() if "expireAfterSeconds" in info]
        self.assertEqual(len(ttl), 1)
        self.assertEqual(ttl[0]["expireAfterSeconds"], 3600)

    def test_senha_certa_de_cadastro_ainda_nao_confirmado_nao_conta_como_falha(self):
        Client().post(
            "/contas/cadastro/",
            {
                "username": "novata",
                "email": "novata@exemplo.com",
                "senha": SENHA_PADRAO,
                "confirmar_senha": SENHA_PADRAO,
                "aceite_politica": "on",
            },
        )
        for _ in range(7):
            resposta = self.entrar_com(SENHA_PADRAO, email="novata@exemplo.com")
            self.assertContains(resposta, "Falta confirmar o seu e-mail")
        self.assertEqual(TentativaLogin.objects.count(), 0)


class LimiteNasTelasDeContaTests(MongoTestCase):
    """Um cookie de sessão roubado não pode servir para adivinhar a senha da
    conta nas telas que pedem a senha de novo."""

    def setUp(self):
        super().setUp()
        self.ana = self.criar_usuario("ana")
        self.entrar(self.ana)

    def trocar_senha(self, senha_atual):
        return self.client.post(
            "/contas/conta/",
            {
                "senha_atual": senha_atual,
                "nova_senha": NOVA_SENHA,
                "confirmar_nova_senha": NOVA_SENHA,
            },
        )

    def trocar_email(self, senha_atual):
        return self.client.post(
            "/contas/conta/",
            {
                "acao": "email",
                "email-novo_email": "ana.nova@exemplo.com",
                "email-senha_atual": senha_atual,
            },
        )

    def excluir(self, senha):
        return self.client.post("/contas/excluir/", {"senha": senha, "confirmacao": "on"})

    def test_trocar_a_senha_trava_depois_de_cinco_erros(self):
        for _ in range(5):
            self.assertContains(self.trocar_senha("errada-errada"), "A senha atual não confere.")
        self.assertContains(self.trocar_senha(SENHA_PADRAO), "Muitas tentativas")
        self.ana.reload()
        self.assertTrue(self.ana.checar_senha(SENHA_PADRAO))

    def test_trocar_o_email_trava_depois_de_cinco_erros(self):
        for _ in range(5):
            self.assertContains(self.trocar_email("errada-errada"), "A senha atual não confere.")
        self.assertContains(self.trocar_email(SENHA_PADRAO), "Muitas tentativas")
        self.assertEqual(len(mail.outbox), 0)

    def test_excluir_a_conta_trava_depois_de_cinco_erros(self):
        for _ in range(5):
            self.assertContains(self.excluir("errada-errada"), "Senha incorreta.")
        self.assertContains(self.excluir(SENHA_PADRAO), "Muitas tentativas")
        self.assertTrue(Usuario.objects(email=EMAIL_ANA).first())

    def test_a_contagem_e_uma_so_para_a_conta_e_vale_tambem_para_o_login(self):
        for _ in range(3):
            self.trocar_senha("errada-errada")
        for _ in range(2):
            self.excluir("errada-errada")
        resposta = Client().post("/contas/login/", {"email": EMAIL_ANA, "senha": SENHA_PADRAO})
        self.assertContains(resposta, "Muitas tentativas")

    def test_acertar_a_senha_atual_zera_a_contagem(self):
        for _ in range(4):
            self.trocar_senha("errada-errada")
        self.assertEqual(self.trocar_senha(SENHA_PADRAO).status_code, 302)
        self.assertEqual(TentativaLogin.objects.count(), 0)


# --------------------------------------------------------------------------
# Sessões
# --------------------------------------------------------------------------


class SessoesTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.criar_usuario("ana")

    def trocar_senha(self, cliente):
        return cliente.post(
            "/contas/conta/",
            {
                "senha_atual": SENHA_PADRAO,
                "nova_senha": NOVA_SENHA,
                "confirmar_nova_senha": NOVA_SENHA,
            },
        )

    def sessao_sem_numero(self):
        """Sessão como as de antes de o número existir: só o id do usuário."""
        sessao = self.client.session
        sessao["usuario_id"] = str(self.ana.id)
        sessao.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key

    def test_o_login_guarda_o_numero_da_sessao(self):
        Client()  # cliente novo, sem sessão
        cliente = Client()
        cliente.post("/contas/login/", {"email": EMAIL_ANA, "senha": SENHA_PADRAO})
        self.assertEqual(cliente.session["sessao_versao"], 0)

    def test_trocar_a_senha_encerra_as_outras_sessoes_e_mantem_esta(self):
        outro_aparelho = Client()
        outro_aparelho.post("/contas/login/", {"email": EMAIL_ANA, "senha": SENHA_PADRAO})
        self.entrar(self.ana)
        self.assertEqual(outro_aparelho.get("/contas/conta/").status_code, 200)

        resposta = self.trocar_senha(self.client)
        self.assertRedirects(resposta, "/contas/conta/", fetch_redirect_response=False)

        self.assertEqual(self.client.get("/contas/conta/").status_code, 200)
        resposta = outro_aparelho.get("/contas/conta/")
        self.assertRedirects(resposta, "/contas/login/", fetch_redirect_response=False)
        self.ana.reload()
        self.assertEqual(self.ana.sessao_versao, 1)

    def test_a_sessao_encerrada_limpa_o_cookie_e_nao_vira_erro(self):
        self.entrar(self.ana)
        Usuario.objects(id=self.ana.id).update_one(inc__sessao_versao=1)
        resposta = self.client.get("/campanhas/")
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("usuario_id", self.client.session)

    def test_sessao_antiga_sem_o_numero_segue_valendo_ate_a_senha_mudar(self):
        self.sessao_sem_numero()
        self.assertEqual(self.client.get("/contas/conta/").status_code, 200)

        self.ana.encerrar_sessoes()
        self.ana.save()
        resposta = self.client.get("/contas/conta/")
        self.assertRedirects(resposta, "/contas/login/", fetch_redirect_response=False)

    def test_sair_apaga_o_numero_da_sessao(self):
        cliente = Client()
        cliente.post("/contas/login/", {"email": EMAIL_ANA, "senha": SENHA_PADRAO})
        cliente.get("/contas/logout/")
        self.assertNotIn("sessao_versao", cliente.session)
        self.assertNotIn("usuario_id", cliente.session)
