"""RNF01 / RNF05 - o site continua rápido e correto com muita gente e muito conteúdo:
listas em páginas, consultas que não carregam o que a tela não usa e operações
que não se atropelam quando várias pessoas agem ao mesmo tempo."""

import datetime
import re
from unittest import mock

import mongomock
from django.test import Client
from mongoengine.queryset.base import BaseQuerySet

from chat.models import MensagemChat
from core.base_testes import MongoTestCase
from notificacoes.models import Notificacao

from . import models, recomendacoes, views
from .models import Campanha


def agora_mais(segundos):
    return datetime.datetime.utcnow() + datetime.timedelta(seconds=segundos)


class ProjecoesUsadas:
    """Anota os campos que cada consulta ao banco pediu (a "projeção") enquanto a
    requisição roda, para conferir que a tela não carrega o que não usa."""

    def __enter__(self):
        self.projecoes = []
        original = mongomock.collection.Collection.find
        projecoes = self.projecoes

        def espiao(colecao, *args, **kwargs):
            if colecao.name == "campanhas":
                projecoes.append(kwargs.get("projection"))
            return original(colecao, *args, **kwargs)

        self.patch = mock.patch.object(mongomock.collection.Collection, "find", espiao)
        self.patch.start()
        return self

    def __exit__(self, *erro):
        self.patch.stop()


def nao_carrega_comentarios(projecao):
    """True se a projeção deixa os comentários de fora: ou os exclui de forma
    explícita, ou pede só alguns campos e eles não estão entre os pedidos."""
    if not projecao:
        return False
    if projecao.get("comentarios") == 0:
        return True
    return all(valor == 1 for valor in projecao.values()) and "comentarios" not in projecao


class ListaEmPaginasTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        for numero in range(30):
            self.criar_campanha(
                self.mestre,
                titulo=f"Mesa {numero:02d}",
                criado_em=agora_mais(numero),  # a de número maior é a mais nova
            )

    def titulos(self, resposta):
        return re.findall(r'class="ficha__titulo"><a [^>]*>(Mesa \d\d)</a>', resposta.content.decode())

    def test_cada_pagina_traz_12_campanhas_das_mais_novas_para_as_mais_antigas(self):
        primeira = self.titulos(Client().get("/campanhas/"))
        self.assertEqual(len(primeira), views.CAMPANHAS_POR_PAGINA)
        self.assertEqual(primeira[0], "Mesa 29")
        self.assertEqual(primeira[-1], "Mesa 18")
        self.assertEqual(len(self.titulos(Client().get("/campanhas/?p=3"))), 6)

    def test_percorrendo_as_paginas_aparecem_todas_uma_so_vez(self):
        vistos = []
        for pagina in (1, 2, 3):
            vistos += self.titulos(Client().get(f"/campanhas/?p={pagina}"))
        self.assertEqual(vistos, [f"Mesa {n:02d}" for n in range(29, -1, -1)])

    def test_datas_iguais_nao_repetem_nem_somem_campanhas_entre_as_paginas(self):
        mesma_hora = agora_mais(0)
        Campanha.objects.update(set__criado_em=mesma_hora)
        vistos = []
        for pagina in (1, 2, 3):
            vistos += self.titulos(Client().get(f"/campanhas/?p={pagina}"))
        self.assertEqual(len(vistos), 30)
        self.assertEqual(len(set(vistos)), 30)

    def test_a_ordem_tem_desempate_pelo_id(self):
        """O MongoDB não garante a ordem entre registros de datas iguais, e sem
        ela uma campanha pode aparecer em duas páginas ou em nenhuma."""
        ordens = []
        original = BaseQuerySet.order_by

        def espiao(consulta, *chaves):
            ordens.append(chaves)
            return original(consulta, *chaves)

        with mock.patch.object(BaseQuerySet, "order_by", espiao):
            Client().get("/campanhas/")
        self.assertIn(("-criado_em", "-id"), ordens)

    def test_mostra_em_que_pagina_esta_e_os_botoes(self):
        resposta = Client().get("/campanhas/?p=2")
        self.assertContains(resposta, "Página 2 de 3")
        self.assertContains(resposta, 'rel="prev"')
        self.assertContains(resposta, 'rel="next"')

    def test_pagina_invalida_vira_a_primeira_e_alem_do_fim_vira_a_ultima(self):
        self.assertEqual(self.titulos(Client().get("/campanhas/?p=abc"))[0], "Mesa 29")
        self.assertContains(Client().get("/campanhas/?p=999"), "Página 3 de 3")

    def test_os_links_das_paginas_guardam_a_busca_e_o_filtro(self):
        resposta = Client().get("/campanhas/?q=mesa&sistema=D%26D+5e")
        self.assertContains(resposta, "q=mesa&amp;sistema=D%26D+5e&amp;p=2")

    def test_o_total_da_busca_conta_todas_e_nao_so_a_pagina(self):
        resposta = Client().get("/campanhas/?q=mesa")
        self.assertContains(resposta, "30 campanhas encontradas")
        self.assertEqual(len(self.titulos(resposta)), 12)

    def test_lista_curta_nao_mostra_botoes(self):
        Campanha.objects.delete()
        self.criar_campanha(self.mestre, titulo="Mesa 00")
        self.assertNotContains(Client().get("/campanhas/"), "Página 1 de")


class ConsultasLevesTests(MongoTestCase):
    """As telas de lista não precisam dos comentários (que podem ser centenas)."""

    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.ana = self.criar_usuario("ana")
        self.campanha = self.criar_campanha(
            self.mestre, jogadores_inscritos_emails=[self.ana.email]
        )
        for numero in range(5):
            self.campanha.adicionar_comentario(self.ana.email, "ana", f"comentário {numero}")
        self.criar_campanha(self.mestre, titulo="Outra mesa")
        self.entrar(self.ana)

    def sem_comentarios(self, url):
        with ProjecoesUsadas() as espiao:
            resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(espiao.projecoes, "nenhuma consulta às campanhas em " + url)
        for projecao in espiao.projecoes:
            self.assertTrue(
                nao_carrega_comentarios(projecao),
                f"consulta que carrega os comentários em {url}: projeção {projecao}",
            )

    def test_lista_publica(self):
        self.sem_comentarios("/campanhas/")

    def test_lista_publica_com_busca(self):
        self.sem_comentarios("/campanhas/?q=mesa")

    def test_minhas_inscricoes(self):
        self.sem_comentarios("/campanhas/inscricoes/")

    def test_minhas_campanhas(self):
        self.entrar(self.mestre)
        self.sem_comentarios("/campanhas/minhas/")

    def test_recomendadas(self):
        self.entrar(self.criar_usuario("carla"))
        self.sem_comentarios("/campanhas/recomendadas/")

    def test_a_pagina_da_campanha_continua_trazendo_os_comentarios(self):
        resposta = self.client.get(f"/campanhas/{self.campanha.id}/")
        self.assertContains(resposta, "comentário 4")


class RecomendacaoComLimiteTests(MongoTestCase):
    def test_so_as_campanhas_abertas_mais_recentes_entram_na_comparacao(self):
        mestre = self.criar_usuario("mestre")
        leitora = self.criar_usuario("leitora")
        for numero in range(6):
            self.criar_campanha(
                mestre, titulo=f"Mesa {numero}", criado_em=agora_mais(numero)
            )
        with mock.patch.object(recomendacoes, "CANDIDATAS_MAX", 3):
            recomendadas = recomendacoes.recomendar_campanhas(leitora, limite=10)
        self.assertEqual(
            sorted(c.titulo for c in recomendadas), ["Mesa 3", "Mesa 4", "Mesa 5"]
        )

    def test_o_perfil_so_le_os_campos_do_texto(self):
        mestre = self.criar_usuario("mestre")
        self.criar_campanha(mestre)
        with ProjecoesUsadas() as espiao:
            recomendacoes._texto_do_perfil(mestre)
        projecoes = [p for p in espiao.projecoes if p]
        self.assertTrue(projecoes)
        for projecao in projecoes:
            self.assertEqual(set(projecao) - {"_id"}, {"sistema_rpg", "titulo", "sinopse"})


class InscricaoSimultaneaTests(MongoTestCase):
    """Duas requisições leem a mesma mesa e agem uma depois da outra: o banco, e
    não a cópia que cada uma leu, decide quem fica com a vaga."""

    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.ana = self.criar_usuario("ana")
        self.beto = self.criar_usuario("beto")
        self.caio = self.criar_usuario("caio")

    def duas_copias(self, campanha):
        return Campanha.objects.get(id=campanha.id), Campanha.objects.get(id=campanha.id)

    def test_a_ultima_vaga_so_vai_para_uma_pessoa(self):
        campanha = self.criar_campanha(
            self.mestre, max_jogadores=2, jogadores_inscritos_emails=[self.ana.email]
        )
        copia_do_beto, copia_do_caio = self.duas_copias(campanha)

        self.assertEqual(
            copia_do_beto.inscrever_jogador(self.beto.email),
            (True, "Inscrição realizada com sucesso."),
        )
        self.assertEqual(
            copia_do_caio.inscrever_jogador(self.caio.email),
            (False, "Não há vagas livres nesta campanha."),
        )

        salva = Campanha.objects.get(id=campanha.id)
        self.assertEqual(salva.jogadores_inscritos_emails, [self.ana.email, self.beto.email])
        self.assertEqual(salva.status, "lotada")
        self.assertEqual(copia_do_caio.jogadores_inscritos_emails, salva.jogadores_inscritos_emails)

    def test_inscricoes_simultaneas_com_vaga_para_todos_nao_perdem_ninguem(self):
        campanha = self.criar_campanha(self.mestre, max_jogadores=3)
        copia_a, copia_b = self.duas_copias(campanha)
        self.assertTrue(copia_a.inscrever_jogador(self.ana.email)[0])
        self.assertTrue(copia_b.inscrever_jogador(self.beto.email)[0])

        salva = Campanha.objects.get(id=campanha.id)
        self.assertEqual(salva.jogadores_inscritos_emails, [self.ana.email, self.beto.email])
        self.assertEqual(salva.status, "aberta")

    def test_a_mesma_pessoa_clicando_duas_vezes_entra_uma_vez(self):
        campanha = self.criar_campanha(self.mestre, max_jogadores=3)
        copia_a, copia_b = self.duas_copias(campanha)
        self.assertTrue(copia_a.inscrever_jogador(self.ana.email)[0])
        self.assertEqual(
            copia_b.inscrever_jogador(self.ana.email),
            (False, "Você já está inscrito nesta campanha."),
        )
        salva = Campanha.objects.get(id=campanha.id)
        self.assertEqual(salva.jogadores_inscritos_emails, [self.ana.email])

    def test_mesa_encerrada_depois_da_leitura_nao_aceita_a_inscricao(self):
        campanha = self.criar_campanha(self.mestre, max_jogadores=3)
        copia_do_jogador = Campanha.objects.get(id=campanha.id)
        campanha.encerrar()
        self.assertEqual(
            copia_do_jogador.inscrever_jogador(self.ana.email),
            (False, "Esta campanha está encerrada e não aceita novas inscrições."),
        )
        self.assertEqual(Campanha.objects.get(id=campanha.id).jogadores_inscritos_emails, [])

    def test_saida_simultanea_da_mesma_pessoa_so_conta_uma_vez(self):
        campanha = self.criar_campanha(
            self.mestre, max_jogadores=2, status="lotada",
            jogadores_inscritos_emails=[self.ana.email, self.beto.email],
        )
        copia_a, copia_b = self.duas_copias(campanha)
        self.assertEqual(copia_a.remover_jogador(self.ana.email), (True, "Inscrição cancelada."))
        self.assertEqual(
            copia_b.remover_jogador(self.ana.email),
            (False, "Você não está inscrito nesta campanha."),
        )
        salva = Campanha.objects.get(id=campanha.id)
        self.assertEqual(salva.jogadores_inscritos_emails, [self.beto.email])
        self.assertEqual(salva.status, "aberta")

    def test_saida_nao_apaga_quem_entrou_enquanto_isso(self):
        campanha = self.criar_campanha(
            self.mestre, max_jogadores=3, jogadores_inscritos_emails=[self.ana.email]
        )
        copia_da_ana, copia_do_beto = self.duas_copias(campanha)
        copia_do_beto.inscrever_jogador(self.beto.email)
        copia_da_ana.remover_jogador(self.ana.email)
        self.assertEqual(
            Campanha.objects.get(id=campanha.id).jogadores_inscritos_emails, [self.beto.email]
        )

    def test_mesa_lotada_reabre_quando_alguem_sai_e_lota_de_novo_quando_alguem_entra(self):
        campanha = self.criar_campanha(
            self.mestre, max_jogadores=2, status="lotada",
            jogadores_inscritos_emails=[self.ana.email, self.beto.email],
        )
        campanha.remover_jogador(self.ana.email)
        self.assertEqual(campanha.status, "aberta")
        campanha.inscrever_jogador(self.caio.email)
        self.assertEqual(campanha.status, "lotada")
        self.assertEqual(Campanha.objects.get(id=campanha.id).status, "lotada")

    def test_mesa_encerrada_continua_encerrada_quando_alguem_sai(self):
        campanha = self.criar_campanha(
            self.mestre, max_jogadores=2, status="encerrada",
            jogadores_inscritos_emails=[self.ana.email],
        )
        campanha.remover_jogador(self.ana.email)
        self.assertEqual(Campanha.objects.get(id=campanha.id).status, "encerrada")

    def test_inscrever_nao_apaga_o_que_outra_requisicao_gravou_na_mesma_mesa(self):
        campanha = self.criar_campanha(self.mestre, max_jogadores=3)
        copia_do_jogador = Campanha.objects.get(id=campanha.id)
        campanha.adicionar_comentario(self.ana.email, "ana", "chego atrasada")
        Campanha.objects(id=campanha.id).update_one(set__titulo="Título novo")
        copia_do_jogador.inscrever_jogador(self.beto.email)

        salva = Campanha.objects.get(id=campanha.id)
        self.assertEqual(salva.titulo, "Título novo")
        self.assertEqual([c.texto for c in salva.comentarios], ["chego atrasada"])
        self.assertEqual(salva.jogadores_inscritos_emails, [self.beto.email])


class ComentariosSimultaneosTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.ana = self.criar_usuario("ana")
        self.campanha = self.criar_campanha(self.mestre)

    def test_comentarios_feitos_ao_mesmo_tempo_ficam_todos(self):
        copia_a = Campanha.objects.get(id=self.campanha.id)
        copia_b = Campanha.objects.get(id=self.campanha.id)
        copia_a.adicionar_comentario("a@exemplo.com", "a", "primeiro")
        copia_b.adicionar_comentario("b@exemplo.com", "b", "segundo")
        salva = Campanha.objects.get(id=self.campanha.id)
        self.assertEqual([c.texto for c in salva.comentarios], ["primeiro", "segundo"])

    def test_devolve_o_comentario_criado(self):
        comentario = self.campanha.adicionar_comentario(self.ana.email, "ana", "oi")
        self.assertEqual(comentario.texto, "oi")
        self.assertEqual(comentario.autor_username, "ana")

    def test_comentar_nao_apaga_a_inscricao_feita_ao_mesmo_tempo(self):
        copia_de_quem_comenta = Campanha.objects.get(id=self.campanha.id)
        self.campanha.inscrever_jogador(self.ana.email)
        copia_de_quem_comenta.adicionar_comentario(self.ana.email, "ana", "entrei!")
        salva = Campanha.objects.get(id=self.campanha.id)
        self.assertEqual(salva.jogadores_inscritos_emails, [self.ana.email])
        self.assertEqual(len(salva.comentarios), 1)

    def test_passado_o_limite_o_comentario_e_recusado(self):
        with mock.patch.object(models, "MAX_COMENTARIOS", 3):
            for numero in range(3):
                self.assertIsNotNone(self.campanha.adicionar_comentario("a@x.com", "a", str(numero)))
            self.assertIsNone(self.campanha.adicionar_comentario("a@x.com", "a", "um a mais"))
        self.assertEqual(len(Campanha.objects.get(id=self.campanha.id).comentarios), 3)

    def test_a_tela_avisa_quando_a_campanha_atingiu_o_limite(self):
        self.entrar(self.ana)
        with mock.patch.object(models, "MAX_COMENTARIOS", 1):
            self.client.post(f"/campanhas/{self.campanha.id}/comentar/", {"texto": "primeiro"})
            resposta = self.client.post(
                f"/campanhas/{self.campanha.id}/comentar/", {"texto": "segundo"}, follow=True
            )
        self.assertContains(resposta, "limite de comentários")
        self.assertEqual(len(Campanha.objects.get(id=self.campanha.id).comentarios), 1)

    def test_a_pagina_mostra_so_os_comentarios_mais_novos_e_avisa(self):
        base = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        comentarios = [
            models.Comentario(
                autor_email="a@x.com", autor_username="a", texto=f"fala {n:03d}",
                criado_em=base + datetime.timedelta(seconds=n),
            )
            for n in range(views.COMENTARIOS_NA_PAGINA + 20)
        ]
        Campanha.objects(id=self.campanha.id).update_one(set__comentarios=comentarios)

        resposta = self.client.get(f"/campanhas/{self.campanha.id}/")
        html = resposta.content.decode()
        self.assertEqual(html.count('<li class="comentario'), views.COMENTARIOS_NA_PAGINA)
        self.assertContains(resposta, "Mostrando os 100 comentários mais recentes, de 120.")
        self.assertIn("fala 119", html)
        self.assertNotIn("fala 019", html)
        self.assertLess(html.index("fala 119"), html.index("fala 118"))  # mais novo primeiro

    def test_poucos_comentarios_nao_mostram_o_aviso(self):
        self.campanha.adicionar_comentario(self.ana.email, "ana", "oi")
        self.assertNotContains(Client().get(f"/campanhas/{self.campanha.id}/"), "Mostrando os")


class AvisosEmPaginasTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.criar_usuario("ana")
        self.entrar(self.ana)
        base = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        for numero in range(65):
            Notificacao(
                destinatario_email=self.ana.email,
                texto=f"aviso {numero:02d}",
                criado_em=base + datetime.timedelta(seconds=numero),
            ).save()
        Notificacao(destinatario_email="outra@exemplo.com", texto="de outra pessoa").save()

    def test_trinta_por_pagina_dos_mais_novos_para_os_mais_antigos(self):
        html = self.client.get("/notificacoes/").content.decode()
        self.assertEqual(html.count('class="notificacao"'), 30)
        self.assertIn("aviso 64", html)
        self.assertNotIn("aviso 34", html)
        self.assertEqual(
            self.client.get("/notificacoes/?p=3").content.decode().count('class="notificacao"'), 5
        )

    def test_nao_mostra_avisos_de_outras_pessoas(self):
        self.assertNotContains(self.client.get("/notificacoes/"), "de outra pessoa")

    def test_abrir_a_lista_marca_tudo_como_lido_inclusive_o_que_esta_em_outras_paginas(self):
        self.assertEqual(Notificacao.objects(destinatario_email=self.ana.email, lida=False).count(), 65)
        self.client.get("/notificacoes/")
        self.assertEqual(Notificacao.objects(destinatario_email=self.ana.email, lida=False).count(), 0)

    def test_mostra_os_botoes_de_pagina(self):
        self.assertContains(self.client.get("/notificacoes/"), "Página 1 de 3")


class IndicesTests(MongoTestCase):
    def chaves(self, documento):
        indices = documento._get_collection().index_information()
        return [tuple(campo for campo, _ in info["key"]) for info in indices.values()]

    def test_campanhas_tem_indices_para_lista_inscricoes_e_status(self):
        chaves = self.chaves(Campanha)
        self.assertIn(("criado_em", "_id"), chaves)
        self.assertIn(("status", "criado_em"), chaves)
        self.assertIn(("jogadores_inscritos_emails",), chaves)

    def test_chat_tem_indice_para_o_historico_da_sala(self):
        self.assertIn(("campanha_id", "criado_em"), self.chaves(MensagemChat))
