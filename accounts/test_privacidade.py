"""RNF03 - política de privacidade, aceite no cadastro e exportação de dados."""

import base64
import datetime
import json

from django.core import mail
from django.test import Client, override_settings

from campanhas.models import Avaliacao, Comentario
from chat.models import MensagemChat
from core import politica
from core.base_testes import MongoTestCase, SENHA_PADRAO
from moderacao.models import ConteudoBloqueado
from notificacoes.models import Notificacao

from .models import CadastroPendente, FotoPerfil, Usuario


class PoliticaDePrivacidadeTests(MongoTestCase):
    def test_pagina_e_publica(self):
        resposta = Client().get("/privacidade/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Política de Privacidade")
        self.assertContains(resposta, politica.VERSAO)

    @override_settings(CONTATO_PRIVACIDADE="privacidade@exemplo.com")
    def test_mostra_o_contato_quando_configurado(self):
        self.assertContains(Client().get("/privacidade/"), "mailto:privacidade@exemplo.com")

    @override_settings(CONTATO_PRIVACIDADE="")
    def test_sem_contato_configurado_nao_mostra_link_de_email_vazio(self):
        resposta = Client().get("/privacidade/")
        self.assertNotContains(resposta, "mailto:")

    def test_rodape_de_todas_as_paginas_tem_o_link(self):
        self.assertContains(Client().get("/"), 'href="/privacidade/"')

    def test_pagina_aponta_para_os_direitos_no_aplicativo(self):
        resposta = Client().get("/privacidade/")
        for rota in ("/contas/exportar/", "/contas/excluir/", "/contas/preferencias/"):
            self.assertContains(resposta, rota)


class AceiteNoCadastroTests(MongoTestCase):
    def dados(self, **mudancas):
        dados = {
            "username": "novata",
            "email": "novata@exemplo.com",
            "senha": SENHA_PADRAO,
            "confirmar_senha": SENHA_PADRAO,
            "aceite_politica": "on",
        }
        dados.update(mudancas)
        return dados

    def test_formulario_mostra_o_link_da_politica_e_a_caixa(self):
        resposta = Client().get("/contas/cadastro/")
        self.assertContains(resposta, "/privacidade/")
        self.assertContains(resposta, 'name="aceite_politica"')

    def test_sem_o_aceite_nao_cria_cadastro_nem_envia_email(self):
        dados = self.dados()
        del dados["aceite_politica"]
        resposta = Client().post("/contas/cadastro/", dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "concordar com a Política de Privacidade")
        self.assertEqual(CadastroPendente.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_com_o_aceite_guarda_o_momento_no_cadastro_pendente(self):
        antes = datetime.datetime.utcnow()
        resposta = Client().post("/contas/cadastro/", self.dados())
        self.assertEqual(resposta.status_code, 302)
        pendente = CadastroPendente.objects.get()
        self.assertIsNotNone(pendente.politica_aceita_em)
        self.assertGreaterEqual(pendente.politica_aceita_em, antes)

    def test_confirmar_o_email_leva_o_aceite_e_a_versao_para_a_conta(self):
        cliente = Client()
        cliente.post("/contas/cadastro/", self.dados())
        pendente = CadastroPendente.objects.get()
        aceite = pendente.politica_aceita_em
        cliente.get(f"/contas/confirmar-email/{self.token_do_email('confirmar-email')}/")
        usuario = Usuario.objects.get(email="novata@exemplo.com")
        self.assertEqual(usuario.politica_aceita_em, aceite)
        self.assertEqual(usuario.politica_versao, politica.VERSAO)


class ExportacaoDeDadosTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.criar_usuario(
            "ana", bio="Mestre de terror.", preferencias={"sistemas": ["D&D 5e"]},
            fuso_horario="America/Sao_Paulo",
            politica_aceita_em=datetime.datetime(2026, 11, 1, 12, 0), politica_versao="2026-11-25",
            token_recuperacao_senha="TOKEN-SECRETO-RECUPERACAO",
            token_confirmacao="TOKEN-SECRETO-CONFIRMACAO",
        )
        self.beto = self.criar_usuario("beto")
        self.caio = self.criar_usuario("caio")

        self.minha_mesa = self.criar_campanha(
            self.ana,
            titulo="Mesa da Ana",
            data_sessao=datetime.datetime(2026, 12, 5, 22, 0),
            jogadores_inscritos_emails=[self.beto.email, self.caio.email],
        )
        self.mesa_do_beto = self.criar_campanha(
            self.beto, titulo="Mesa do Beto", jogadores_inscritos_emails=[self.ana.email]
        )

        # um comentário da Ana e um do Beto na mesma campanha
        self.mesa_do_beto.comentarios = [
            Comentario(autor_email=self.ana.email, autor_username="ana", texto="Comentário da Ana"),
            Comentario(autor_email=self.beto.email, autor_username="beto", texto="Comentário do Beto"),
        ]
        self.mesa_do_beto.save()

        for autor, texto in ((self.ana, "Chat da Ana"), (self.beto, "Chat do Beto")):
            MensagemChat.objects.create(
                campanha_id=str(self.mesa_do_beto.id), autor_email=autor.email,
                autor_username=autor.username, texto=texto,
            )

        Avaliacao.objects.create(
            campanha_id=str(self.mesa_do_beto.id), campanha_titulo="Mesa do Beto",
            avaliador_email=self.ana.email, avaliador_username="ana",
            avaliado_email=self.beto.email, avaliado_username="beto",
            papel_avaliado="mestre", nota=4, comentario="Feita pela Ana",
        )
        Avaliacao.objects.create(
            campanha_id=str(self.minha_mesa.id), campanha_titulo="Mesa da Ana",
            avaliador_email=self.beto.email, avaliador_username="beto",
            avaliado_email=self.ana.email, avaliado_username="ana",
            papel_avaliado="mestre", nota=5, comentario="Recebida do Beto",
        )
        Notificacao.objects.create(destinatario_email=self.ana.email, texto="Aviso para a Ana")
        Notificacao.objects.create(destinatario_email=self.beto.email, texto="Aviso para o Beto")
        ConteudoBloqueado.objects.create(
            autor_email=self.ana.email, texto_original="texto barrado da Ana",
            motivo="termo ofensivo", origem="chat:1",
        )
        ConteudoBloqueado.objects.create(
            autor_email=self.beto.email, texto_original="texto barrado do Beto",
            motivo="termo ofensivo", origem="chat:1",
        )

    def baixar(self, usuario=None):
        self.entrar(usuario or self.ana)
        resposta = self.client.post("/contas/exportar/")
        self.assertEqual(resposta.status_code, 200)
        return resposta

    def dados(self, usuario=None):
        return json.loads(self.baixar(usuario).content)

    # -- acesso --------------------------------------------------------------

    def test_exige_login_para_ver_a_pagina_e_para_baixar(self):
        for metodo in (Client().get, Client().post):
            resposta = metodo("/contas/exportar/")
            self.assertEqual(resposta.status_code, 302)
            self.assertIn("/contas/login/", resposta["Location"])

    def test_pagina_de_exportacao_abre_para_quem_esta_logado(self):
        self.entrar(self.ana)
        resposta = self.client.get("/contas/exportar/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Baixar meus dados")

    def test_get_nao_baixa_nada(self):
        self.entrar(self.ana)
        self.assertNotIn("attachment", self.client.get("/contas/exportar/").get("Content-Disposition", ""))

    def test_cabecalhos_do_download(self):
        resposta = self.baixar()
        self.assertEqual(resposta["Content-Type"], "application/json; charset=utf-8")
        self.assertRegex(
            resposta["Content-Disposition"],
            r'^attachment; filename="sessao-zero-meus-dados-\d{4}-\d{2}-\d{2}\.json"$',
        )
        self.assertIn("no-store", resposta["Cache-Control"])

    # -- conteúdo ------------------------------------------------------------

    def test_conta_e_preferencias(self):
        conta = self.dados()["conta"]
        self.assertEqual(conta["nome_de_usuario"], "ana")
        self.assertEqual(conta["email"], self.ana.email)
        self.assertEqual(conta["biografia"], "Mestre de terror.")
        self.assertEqual(conta["fuso_horario"], "America/Sao_Paulo")
        self.assertEqual(conta["preferencias"], {"sistemas": ["D&D 5e"]})
        self.assertEqual(
            conta["politica_de_privacidade"],
            {"aceita_em": "2026-11-01T12:00:00Z", "versao": "2026-11-25"},
        )

    def test_conta_antiga_sem_aceite_exporta_com_valores_vazios(self):
        conta = self.dados(self.beto)["conta"]
        self.assertEqual(
            conta["politica_de_privacidade"], {"aceita_em": None, "versao": None}
        )

    def test_campanhas_que_mestro_trazem_so_a_contagem_de_inscritos(self):
        dados = self.dados()
        (mesa,) = dados["campanhas_que_mestro"]
        self.assertEqual(mesa["titulo"], "Mesa da Ana")
        self.assertEqual(mesa["jogadores_inscritos"], 2)
        self.assertEqual(mesa["data_da_primeira_sessao"], "2026-12-05T22:00:00Z")

    def test_campanhas_em_que_estou_inscrito(self):
        (mesa,) = self.dados()["campanhas_em_que_estou_inscrito"]
        self.assertEqual((mesa["titulo"], mesa["mestre"]), ("Mesa do Beto", "beto"))

    def test_so_os_meus_comentarios_e_mensagens(self):
        dados = self.dados()
        self.assertEqual([c["texto"] for c in dados["meus_comentarios"]], ["Comentário da Ana"])
        (msg,) = dados["minhas_mensagens_de_chat"]
        self.assertEqual((msg["texto"], msg["campanha"]), ("Chat da Ana", "Mesa do Beto"))

    def test_avaliacoes_feitas_e_recebidas(self):
        dados = self.dados()
        (feita,) = dados["avaliacoes_que_fiz"]
        (recebida,) = dados["avaliacoes_que_recebi"]
        self.assertEqual((feita["avaliado"], feita["nota"], feita["comentario"]), ("beto", 4, "Feita pela Ana"))
        self.assertEqual((recebida["avaliador"], recebida["nota"], recebida["comentario"]), ("beto", 5, "Recebida do Beto"))

    def test_avisos_e_textos_barrados_sao_so_os_meus(self):
        dados = self.dados()
        self.assertEqual([a["texto"] for a in dados["avisos_recebidos"]], ["Aviso para a Ana"])
        self.assertEqual(
            [b["texto"] for b in dados["textos_barrados_pela_moderacao"]], ["texto barrado da Ana"]
        )

    def test_foto_de_perfil_vai_em_base64(self):
        jpeg = b"\xff\xd8\xff\xe0dados-de-uma-foto"
        FotoPerfil(usuario_id=str(self.ana.id), dados=jpeg).save()
        self.ana.tem_foto = True
        self.ana.save()
        conta = self.dados()["conta"]
        self.assertEqual(base64.b64decode(conta["foto_de_perfil_jpeg_base64"]), jpeg)
        self.assertTrue(conta["avatar"]["tem_foto"])

    def test_sem_foto_nao_ha_o_campo(self):
        self.assertNotIn("foto_de_perfil_jpeg_base64", self.dados()["conta"])

    def test_usuario_sem_nada_exporta_listas_vazias(self):
        dados = self.dados(self.caio)
        self.assertEqual(dados["campanhas_que_mestro"], [])
        self.assertEqual(dados["avaliacoes_que_fiz"], [])
        self.assertEqual(dados["avisos_recebidos"], [])

    # -- o que NÃO pode sair -------------------------------------------------

    def test_nao_exporta_senha_nem_tokens(self):
        texto = self.baixar().content.decode()
        self.assertNotIn(self.ana.senha_hash, texto)
        self.assertNotIn("pbkdf2", texto)
        self.assertNotIn("senha", json.loads(texto)["conta"])
        self.assertNotIn("TOKEN-SECRETO-RECUPERACAO", texto)
        self.assertNotIn("TOKEN-SECRETO-CONFIRMACAO", texto)

    def test_nao_exporta_o_email_de_outras_pessoas(self):
        texto = self.baixar().content.decode()
        self.assertNotIn(self.beto.email, texto)
        self.assertNotIn(self.caio.email, texto)

    def test_nao_exporta_o_conteudo_de_outras_pessoas(self):
        texto = self.baixar().content.decode()
        for alheio in ("Comentário do Beto", "Chat do Beto", "Aviso para o Beto", "texto barrado do Beto", "Feita pela Ana de outra"):
            self.assertNotIn(alheio, texto)

    def test_cada_pessoa_exporta_so_o_que_e_seu(self):
        beto = self.dados(self.beto)
        self.assertEqual(beto["conta"]["nome_de_usuario"], "beto")
        self.assertEqual([c["texto"] for c in beto["meus_comentarios"]], ["Comentário do Beto"])
        self.assertNotIn("Comentário da Ana", json.dumps(beto, ensure_ascii=False))

    def test_o_arquivo_e_json_valido_com_acentos_legiveis(self):
        texto = self.baixar().content.decode("utf-8")
        self.assertIn("Comentário da Ana", texto)  # sem á
        self.assertTrue(json.loads(texto)["gerado_em"].endswith("Z"))


class MinhaContaLinksTests(MongoTestCase):
    def test_minha_conta_leva_ao_perfil_a_exportacao_e_a_politica(self):
        ana = self.criar_usuario("ana")
        self.entrar(ana)
        pagina = self.client.get("/contas/conta/").content.decode()
        for rota in ("/contas/u/ana/", "/contas/exportar/", "/privacidade/"):
            self.assertIn(rota, pagina)
