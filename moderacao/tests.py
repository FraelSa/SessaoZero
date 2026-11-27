"""RNF04 - moderação: o filtro, os campos que ele cobre e o painel de revisão."""

import datetime
import tempfile
from pathlib import Path

from django.core import mail
from django.test import SimpleTestCase, override_settings

from accounts.models import CadastroPendente
from campanhas.models import Campanha
from campanhas.tests import dados_do_formulario
from core.base_testes import SENHA_PADRAO, MongoTestCase

from . import filtros
from .models import RETENCAO_DIAS, ConteudoBloqueado
from .servicos import AUTOR_ANONIMO, registrar_bloqueio


class FiltroDeTextoTests(SimpleTestCase):
    def aceito(self, texto):
        return filtros.moderar_texto(texto)[0]

    def test_barra_os_termos_da_lista_nas_formas_comuns(self):
        for texto in (
            "Você é um idiota",
            "seus idiotas",
            "um imbecil",
            "seus imbecis",
            "que burra",
            "burros",
            "FDP",
            "Vai se foder",
            "vai   tomar no   cu",
            "sapatão",
            "lixo humano",
        ):
            with self.subTest(texto=texto):
                self.assertFalse(self.aceito(texto))

    def test_ignora_maiusculas_acentos_e_letras_repetidas(self):
        for texto in ("IDIOTA", "Otária", "ARROMBADO", "iiiiidiotaaa", "buuuurro", "desgraçado"):
            with self.subTest(texto=texto):
                self.assertFalse(self.aceito(texto))

    def test_enxerga_numeros_e_simbolos_no_lugar_de_letras(self):
        for texto in ("1d10t4", "@rrombado", "arr0mb4d0", "b4b4c4", "v14d0"):
            with self.subTest(texto=texto):
                self.assertFalse(self.aceito(texto))

    def test_enxerga_letras_separadas(self):
        for texto in ("i d i o t a", "i.d.i.o.t.a", "i-d-i-o-t-a", "b u r r o"):
            with self.subTest(texto=texto):
                self.assertFalse(self.aceito(texto))

    def test_numero_depois_da_palavra_nao_esconde_o_termo(self):
        # "idiota1" não pode virar "idiotai": o número só vira letra na outra leitura.
        for texto in ("idiota1", "idiota123", "burro2000", "idiota3"):
            with self.subTest(texto=texto):
                self.assertFalse(self.aceito(texto))

    def test_compara_palavras_inteiras_e_nao_pedacos(self):
        # Antes, "burro" dentro de outra palavra também barrava.
        for texto in ("estou aburrido", "que burrice", "idiotice", "o homem viajou", "bailarino"):
            with self.subTest(texto=texto):
                self.assertTrue(self.aceito(texto))

    def test_usos_legitimos_da_lista_de_excecoes_passam(self):
        self.assertTrue(self.aceito("Os burros de carga atravessaram a ponte."))
        self.assertTrue(self.aceito("Um burro de carga e dois cavalos."))

    def test_a_excecao_nao_protege_o_resto_do_texto(self):
        self.assertFalse(self.aceito("Um burro de carga e você, um burro."))

    def test_textos_comuns_de_mesa_de_rpg_passam(self):
        for texto in (
            "Role 1d10 de dano e 2d6+3 de ataque.",
            "D&D 5e: Curse of Strahd",
            "Nível 5, CA 15, 3 jogadores.",
            "O mongol Gengis Khan unificou as tribos.",
            "Caçamos um veado na floresta.",
            "Olá, pessoal! Quem vem na sexta?",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(self.aceito(texto))

    def test_o_motivo_e_a_mensagem_continuam_prontos_para_o_usuario(self):
        self.assertEqual(
            filtros.moderar_texto("idiota"),
            (False, "Sua mensagem contém um termo não permitido na Sessão Zero."),
        )
        self.assertEqual(filtros.moderar_texto("Olá, tudo bem?"), (True, ""))

    def test_barra_texto_em_caixa_alta_e_excesso_de_links(self):
        self.assertFalse(self.aceito("ISSO É UM ABSURDO TOTAL"))
        self.assertFalse(self.aceito("http://a.com http://b.com"))
        self.assertTrue(self.aceito("Veja http://a.com"))

    def test_a_sinopse_aceita_ate_tres_links(self):
        tres = "Discord https://a.com, mesa https://b.com, ficha https://c.com"
        quatro = tres + " e https://d.com"
        self.assertTrue(filtros.moderar_sinopse(tres)[0])
        self.assertFalse(filtros.moderar_sinopse(quatro)[0])
        self.assertFalse(filtros.moderar_texto(tres)[0])  # chat e comentário seguem com 1

    def test_nomes_so_conferem_os_termos(self):
        # Maiúsculas e vários links não são problema num nome ou título.
        for nome in ("DRAGAO_NEGRO", "CALL OF CTHULHU", "D&D 5e"):
            with self.subTest(nome=nome):
                self.assertEqual(filtros.moderar_nome(nome), (True, ""))
        aceito, motivo = filtros.moderar_nome("xX_idiota_Xx")
        self.assertFalse(aceito)
        self.assertIn("termo não permitido", motivo)


class ListaDeTermosTests(SimpleTestCase):
    def test_le_o_arquivo_ignorando_comentarios_e_linhas_vazias(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "termos.txt"
            arquivo.write_text("# comentário\n\nGrosseria\n  Ofensa Ácida  \n", encoding="utf-8")
            self.assertEqual(filtros.ler_termos(arquivo), ["grosseria", "ofensa acida"])

    def test_sem_o_arquivo_usa_a_lista_de_emergencia(self):
        termos = filtros.ler_termos("/nao/existe/termos.txt")
        self.assertIn("idiota", termos)
        self.assertIn("burro", termos)

    def test_o_arquivo_do_projeto_existe_e_nao_esta_vazio(self):
        termos = filtros.ler_termos()
        self.assertGreaterEqual(len(termos), 15)
        # Todos já normalizados: sem acento, sem maiúscula.
        for termo in termos:
            self.assertEqual(termo, filtros.normalizar(termo))

    def test_plural_e_feminino_saem_do_termo_no_singular(self):
        self.assertEqual(
            filtros._formas("burro"), {"burro", "burros", "burra", "burras", "burros"}
        )
        self.assertIn("imbecis", filtros._formas("imbecil"))
        self.assertIn("animais", filtros._formas("animal"))
        # Frase: vale como foi escrita.
        self.assertEqual(filtros._formas("filho da puta"), {"filho da puta"})


class CamposModeradosTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.entrar(self.mestre)

    def criar(self, **mudancas):
        return self.client.post("/campanhas/nova/", dados_do_formulario(**mudancas))

    def test_titulo_barrado_nao_cria_a_campanha_e_fica_registrado(self):
        resposta = self.criar(titulo="Mesa dos idiotas")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Campanha.objects.count(), 0)
        self.assertContains(resposta, "termo não permitido")
        bloqueio = ConteudoBloqueado.objects.get()
        self.assertEqual(bloqueio.origem, "campanha:titulo")
        self.assertEqual(bloqueio.autor_email, self.mestre.email)
        self.assertEqual(bloqueio.texto_original, "Mesa dos idiotas")

    def test_sinopse_barrada_e_o_registro_cabe_no_limite(self):
        sinopse_longa = "Uma aventura longa. " * 70 + "Seu idiota."  # bem mais de 1000 letras
        self.assertGreater(len(sinopse_longa), 1000)
        resposta = self.criar(sinopse=sinopse_longa)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Campanha.objects.count(), 0)
        bloqueio = ConteudoBloqueado.objects.get()
        self.assertEqual(bloqueio.origem, "campanha:sinopse")
        self.assertEqual(len(bloqueio.texto_original), 1000)

    def test_nome_de_sistema_proprio_barrado(self):
        resposta = self.criar(sistema_rpg="Sistema Próprio", sistema_proprio="Regras do babaca")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Campanha.objects.count(), 0)
        self.assertEqual(ConteudoBloqueado.objects.get().origem, "campanha:sistema")

    def test_titulo_em_maiusculas_e_sinopse_com_links_passam(self):
        sinopse = "Entre no Discord https://a.com e veja a mesa https://b.com antes."
        resposta = self.criar(titulo="A MALDIÇÃO DE STRAHD", sinopse=sinopse)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Campanha.objects.count(), 1)
        self.assertEqual(ConteudoBloqueado.objects.count(), 0)

    def test_editar_so_confere_o_que_mudou(self):
        # Texto antigo com um termo (de antes do filtro): editar outra coisa não é barrado.
        campanha = self.criar_campanha(self.mestre, titulo="Os idiotas do vale")
        resposta = self.client.post(
            f"/campanhas/{campanha.id}/editar/",
            dados_do_formulario(titulo="Os idiotas do vale", max_jogadores="5"),
        )
        self.assertEqual(resposta.status_code, 302)
        campanha.reload()
        self.assertEqual(campanha.max_jogadores, 5)
        self.assertEqual(ConteudoBloqueado.objects.count(), 0)

    def test_editar_para_um_titulo_barrado_e_recusado(self):
        campanha = self.criar_campanha(self.mestre)
        resposta = self.client.post(
            f"/campanhas/{campanha.id}/editar/", dados_do_formulario(titulo="Mesa dos babacas")
        )
        self.assertEqual(resposta.status_code, 200)
        campanha.reload()
        self.assertEqual(campanha.titulo, "A Maldição de Strahd")
        self.assertEqual(ConteudoBloqueado.objects.get().origem, "campanha:titulo")

    def test_cadastro_com_nome_de_usuario_barrado(self):
        self.client.cookies.clear()
        resposta = self.client.post(
            "/contas/cadastro/",
            {
                "username": "idiota_2000",
                "email": "novo@exemplo.com",
                "senha": SENHA_PADRAO,
                "confirmar_senha": SENHA_PADRAO,
                "aceite_politica": "on",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(CadastroPendente.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        bloqueio = ConteudoBloqueado.objects.get()
        self.assertEqual(bloqueio.origem, "cadastro:usuario")
        # O e-mail digitado por quem ainda não tem conta não é guardado.
        self.assertEqual(bloqueio.autor_email, AUTOR_ANONIMO)
        self.assertNotIn("novo@exemplo.com", str(bloqueio.to_json()))

    def test_troca_de_nome_de_usuario_barrada(self):
        resposta = self.client.post(
            "/contas/conta/",
            {"acao": "usuario", "usuario-novo_username": "babaca99"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.mestre.reload()
        self.assertEqual(self.mestre.username, "mestre")
        self.assertEqual(ConteudoBloqueado.objects.get().origem, "perfil:usuario")

    def test_registrar_bloqueio_corta_o_texto_no_tamanho_do_registro(self):
        registro = registrar_bloqueio("a@b.com", "x" * 5000, "motivo", "teste")
        self.assertEqual(len(registro.texto_original), 1000)


@override_settings(MODERADORES_EMAILS=["mod@exemplo.com"])
class PainelDeModeracaoTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.moderador = self.criar_usuario("mod", email="mod@exemplo.com")
        self.outro = self.criar_usuario("comum")

    def bloquear(self, texto="algo barrado", origem="chat:abc", autor="alguem@exemplo.com", **extras):
        return ConteudoBloqueado.objects.create(
            autor_email=autor, texto_original=texto, motivo="motivo", origem=origem, **extras
        )

    # -- acesso -------------------------------------------------------------

    def test_visitante_vai_para_o_login(self):
        resposta = self.client.get("/moderacao/")
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/contas/login/", resposta["Location"])

    def test_quem_nao_e_moderador_recebe_404(self):
        self.entrar(self.outro)
        self.assertEqual(self.client.get("/moderacao/").status_code, 404)
        bloqueio = self.bloquear()
        resposta = self.client.post(
            f"/moderacao/{bloqueio.id}/revisar/", {"decisao": "correto"}
        )
        self.assertEqual(resposta.status_code, 404)
        bloqueio.reload()
        self.assertFalse(bloqueio.revisado)

    @override_settings(MODERADORES_EMAILS=[])
    def test_sem_moderadores_configurados_ninguem_entra(self):
        self.entrar(self.moderador)
        self.assertEqual(self.client.get("/moderacao/").status_code, 404)

    @override_settings(MODERADORES_EMAILS=["mod@exemplo.com"])
    def test_a_comparacao_do_e_mail_ignora_maiusculas(self):
        from .permissoes import eh_moderador

        self.moderador.email = "MOD@Exemplo.com"
        self.assertTrue(eh_moderador(self.moderador))
        self.assertFalse(eh_moderador(None))

    def test_o_menu_so_mostra_o_link_para_moderadores(self):
        self.bloquear()
        self.entrar(self.outro)
        self.assertNotContains(self.client.get("/"), "/moderacao/")
        self.entrar(self.moderador)
        resposta = self.client.get("/")
        self.assertContains(resposta, 'href="/moderacao/"')
        self.assertContains(resposta, "Moderação (1)")

    # -- lista --------------------------------------------------------------

    def test_mostra_so_os_pendentes_por_padrao(self):
        self.bloquear("texto pendente")
        self.bloquear("texto revisado", revisado_em=datetime.datetime.utcnow(), decisao="correto", revisado_por="mod")
        self.entrar(self.moderador)
        resposta = self.client.get("/moderacao/")
        self.assertContains(resposta, "texto pendente")
        self.assertNotContains(resposta, "texto revisado")
        revisados = self.client.get("/moderacao/?estado=revisados")
        self.assertContains(revisados, "texto revisado")
        self.assertNotContains(revisados, "texto pendente")
        todos = self.client.get("/moderacao/?estado=todos")
        self.assertContains(todos, "texto pendente")
        self.assertContains(todos, "texto revisado")

    def test_texto_do_usuario_e_escapado(self):
        self.bloquear("<script>alert(1)</script>")
        self.entrar(self.moderador)
        resposta = self.client.get("/moderacao/")
        self.assertNotContains(resposta, "<script>alert(1)</script>")
        self.assertContains(resposta, "&lt;script&gt;")

    def test_filtra_por_origem(self):
        self.bloquear("do chat", origem="chat:1")
        self.bloquear("da bio", origem="perfil:bio")
        self.entrar(self.moderador)
        resposta = self.client.get("/moderacao/?origem=perfil")
        self.assertContains(resposta, "da bio")
        self.assertNotContains(resposta, "do chat")
        self.assertContains(resposta, "Biografia")

    def test_filtros_invalidos_voltam_ao_padrao(self):
        self.bloquear("qualquer")
        self.entrar(self.moderador)
        resposta = self.client.get("/moderacao/?estado=zzz&origem=zzz&p=abc")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "qualquer")

    def test_divide_em_paginas(self):
        for numero in range(60):
            self.bloquear(f"registro numero {numero:02d}")
        self.entrar(self.moderador)
        primeira = self.client.get("/moderacao/")
        self.assertContains(primeira, "Página 1 de 3")
        self.assertContains(primeira, "p=2")
        # Os mais novos primeiro: o 59 é o último criado.
        self.assertContains(primeira, "registro numero 59")
        self.assertNotContains(primeira, "registro numero 00")
        ultima = self.client.get("/moderacao/?p=3")
        self.assertContains(ultima, "registro numero 00")
        # Página além do fim vira a última; os filtros ficam nos links.
        alem = self.client.get("/moderacao/?estado=pendentes&p=99")
        self.assertContains(alem, "Página 3 de 3")
        self.assertContains(alem, "estado=pendentes&amp;p=2")

    def test_destaca_quem_foi_barrado_varias_vezes_na_semana(self):
        for _ in range(3):
            self.bloquear(autor="insistente@exemplo.com")
        self.bloquear(autor="eventual@exemplo.com")
        antigo = self.bloquear(autor="antigo@exemplo.com")
        antigo2 = self.bloquear(autor="antigo@exemplo.com")
        antigo3 = self.bloquear(autor="antigo@exemplo.com")
        velho = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        for registro in (antigo, antigo2, antigo3):
            ConteudoBloqueado.objects(id=registro.id).update(set__criado_em=velho)
        self.entrar(self.moderador)
        resposta = self.client.get("/moderacao/")
        self.assertContains(resposta, "insistente@exemplo.com: 3 vezes")
        self.assertNotContains(resposta, "eventual@exemplo.com: ")
        self.assertNotContains(resposta, "antigo@exemplo.com: ")

    # -- revisão ------------------------------------------------------------

    def revisar(self, bloqueio, decisao, **extras):
        return self.client.post(
            f"/moderacao/{bloqueio.id}/revisar/", {"decisao": decisao, **extras}
        )

    def test_marca_como_correto_ou_falso_positivo(self):
        bloqueio = self.bloquear()
        self.entrar(self.moderador)
        resposta = self.revisar(bloqueio, "falso_positivo")
        self.assertEqual(resposta.status_code, 302)
        bloqueio.reload()
        self.assertEqual(bloqueio.decisao, "falso_positivo")
        self.assertEqual(bloqueio.revisado_por, "mod")
        self.assertIsNotNone(bloqueio.revisado_em)

        self.revisar(bloqueio, "correto")
        bloqueio.reload()
        self.assertEqual(bloqueio.decisao, "correto")

    def test_desfazer_a_revisao_devolve_o_registro_aos_pendentes(self):
        bloqueio = self.bloquear(revisado_em=datetime.datetime.utcnow(), decisao="correto", revisado_por="mod")
        self.entrar(self.moderador)
        self.revisar(bloqueio, "pendente")
        bloqueio.reload()
        self.assertFalse(bloqueio.revisado)
        self.assertIsNone(bloqueio.decisao)
        self.assertIsNone(bloqueio.revisado_por)

    def test_decisao_invalida_e_registro_inexistente(self):
        bloqueio = self.bloquear()
        self.entrar(self.moderador)
        self.revisar(bloqueio, "apagar-tudo")
        bloqueio.reload()
        self.assertFalse(bloqueio.revisado)
        self.assertEqual(self.revisar(ConteudoBloqueado(id="000000000000000000000000"), "correto").status_code, 404)
        self.assertEqual(
            self.client.post("/moderacao/nao-e-um-id/revisar/", {"decisao": "correto"}).status_code, 404
        )

    def test_revisar_exige_post(self):
        bloqueio = self.bloquear()
        self.entrar(self.moderador)
        self.assertEqual(self.client.get(f"/moderacao/{bloqueio.id}/revisar/").status_code, 405)

    def test_volta_para_a_lista_de_onde_veio_mas_nunca_para_outro_site(self):
        bloqueio = self.bloquear()
        self.entrar(self.moderador)
        resposta = self.revisar(bloqueio, "correto", volta="/moderacao/?estado=todos&p=2")
        self.assertEqual(resposta["Location"], "/moderacao/?estado=todos&p=2")
        for destino in ("https://exemplo.com/golpe", "//exemplo.com/golpe", "/contas/conta/"):
            with self.subTest(destino=destino):
                resposta = self.revisar(bloqueio, "correto", volta=destino)
                self.assertEqual(resposta["Location"], "/moderacao/")

    def test_a_revisao_exige_o_token_de_csrf(self):
        from django.test import Client

        bloqueio = self.bloquear()
        cliente = Client(enforce_csrf_checks=True)
        sessao = cliente.session
        sessao["usuario_id"] = str(self.moderador.id)
        sessao.save()
        from django.conf import settings

        cliente.cookies[settings.SESSION_COOKIE_NAME] = sessao.session_key
        resposta = cliente.post(f"/moderacao/{bloqueio.id}/revisar/", {"decisao": "correto"})
        self.assertEqual(resposta.status_code, 403)
        bloqueio.reload()
        self.assertFalse(bloqueio.revisado)


class RetencaoDoRegistroTests(MongoTestCase):
    def test_o_banco_apaga_o_registro_sozinho_depois_do_prazo(self):
        ConteudoBloqueado.objects.create(
            autor_email="a@b.com", texto_original="x", motivo="m", origem="chat:1"
        )
        indices = ConteudoBloqueado._get_collection().index_information()
        ttl = [info for info in indices.values() if "expireAfterSeconds" in info]
        self.assertEqual(len(ttl), 1)
        self.assertEqual(ttl[0]["key"], [("criado_em", 1)])
        self.assertEqual(ttl[0]["expireAfterSeconds"], RETENCAO_DIAS * 24 * 3600)

    def test_o_prazo_e_de_180_dias(self):
        # A Política de Privacidade promete este prazo.
        self.assertEqual(RETENCAO_DIAS, 180)
