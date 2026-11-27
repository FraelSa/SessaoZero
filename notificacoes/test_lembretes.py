"""RF08 - lembretes de sessão: o que é enviado, para quem, uma vez só, e como o
agendador externo os dispara (comando e endereço protegido por token)."""

import datetime
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import Client, override_settings

from campanhas.models import Campanha
from core.base_testes import MongoTestCase

from .lembretes import enviar_lembretes
from .models import Notificacao

AGORA = datetime.datetime(2026, 11, 27, 12, 0)  # UTC; em Salvador são 09:00
EM = datetime.timedelta


class BaseLembrete(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.mestre = self.criar_usuario("mestre")
        self.ana = self.criar_usuario("ana")
        self.beto = self.criar_usuario("beto")

    def mesa(self, **extras):
        extras.setdefault("titulo", "A Maldição de Strahd")
        extras.setdefault("data_sessao", AGORA + EM(hours=5))
        extras.setdefault("jogadores_inscritos_emails", [self.ana.email, self.beto.email])
        return self.criar_campanha(self.mestre, **extras)

    def total_de_avisos(self):
        return Notificacao.objects.count()


class QuemRecebeELembreteTests(BaseLembrete):
    def test_avisa_o_mestre_e_cada_inscrito_quando_falta_menos_de_24h(self):
        self.mesa()
        lembradas = enviar_lembretes(agora=AGORA)
        self.assertEqual(
            [(i["titulo"], i["avisos"]) for i in lembradas], [("A Maldição de Strahd", 3)]
        )
        aviso = (
            'Lembrete: a sessão de "A Maldição de Strahd" acontece em '
            "27/11/2026 às 14:00 (Salvador, Bahia)."
        )
        for pessoa in (self.mestre, self.ana, self.beto):
            self.assertEqual(self.textos_das_notificacoes(pessoa), [aviso])

    def test_o_aviso_leva_para_a_campanha(self):
        campanha = self.mesa()
        enviar_lembretes(agora=AGORA)
        aviso = Notificacao.objects(destinatario_email=self.ana.email).first()
        self.assertEqual(aviso.url, f"/campanhas/{campanha.id}/")
        self.assertFalse(aviso.lida)

    def test_nao_avisa_quem_nao_participa(self):
        de_fora = self.criar_usuario("defora")
        self.mesa()
        enviar_lembretes(agora=AGORA)
        self.assertEqual(self.textos_das_notificacoes(de_fora), [])

    def test_mesa_sem_inscritos_avisa_so_o_mestre(self):
        self.mesa(jogadores_inscritos_emails=[])
        enviar_lembretes(agora=AGORA)
        self.assertEqual(self.total_de_avisos(), 1)
        self.assertEqual(len(self.textos_das_notificacoes(self.mestre)), 1)

    def test_depois_de_sair_da_mesa_a_pessoa_nao_e_lembrada(self):
        campanha = self.mesa()
        campanha.remover_jogador(self.ana.email)
        enviar_lembretes(agora=AGORA)
        self.assertEqual(self.textos_das_notificacoes(self.ana), [])
        self.assertEqual(len(self.textos_das_notificacoes(self.beto)), 1)


class QuandoLembrarTests(BaseLembrete):
    def test_nao_avisa_quando_falta_mais_de_24h(self):
        self.mesa(data_sessao=AGORA + EM(hours=25))
        self.assertEqual(enviar_lembretes(agora=AGORA), [])
        self.assertEqual(self.total_de_avisos(), 0)

    def test_avisa_logo_dentro_do_limite_de_24h(self):
        self.mesa(data_sessao=AGORA + EM(hours=24))
        self.assertEqual(len(enviar_lembretes(agora=AGORA)), 1)

    def test_nao_avisa_sessao_que_ja_aconteceu(self):
        self.mesa(data_sessao=AGORA - EM(hours=1))
        self.assertEqual(enviar_lembretes(agora=AGORA), [])

    def test_nao_avisa_campanha_encerrada(self):
        self.mesa(status="encerrada")
        self.assertEqual(enviar_lembretes(agora=AGORA), [])

    def test_nao_avisa_campanha_sem_data(self):
        self.mesa(data_sessao=None)
        self.assertEqual(enviar_lembretes(agora=AGORA), [])

    def test_mesa_lotada_tambem_e_lembrada(self):
        self.mesa(max_jogadores=2, status="lotada")
        self.assertEqual(len(enviar_lembretes(agora=AGORA)), 1)

    def test_a_antecedencia_pode_ser_mudada(self):
        self.mesa(data_sessao=AGORA + EM(hours=30))
        self.assertEqual(enviar_lembretes(agora=AGORA), [])
        self.assertEqual(len(enviar_lembretes(agora=AGORA, antecedencia=EM(hours=48))), 1)

    def test_cada_campanha_e_avaliada_por_si(self):
        self.mesa(titulo="Perto", data_sessao=AGORA + EM(hours=2))
        self.mesa(titulo="Longe", data_sessao=AGORA + EM(days=3))
        lembradas = enviar_lembretes(agora=AGORA)
        self.assertEqual([i["titulo"] for i in lembradas], ["Perto"])


class UmaVezPorSessaoTests(BaseLembrete):
    def test_chamar_de_novo_nao_avisa_outra_vez(self):
        self.mesa()
        enviar_lembretes(agora=AGORA)
        antes = self.total_de_avisos()
        self.assertEqual(enviar_lembretes(agora=AGORA + EM(hours=1)), [])
        self.assertEqual(self.total_de_avisos(), antes)

    def test_a_sessao_lembrada_fica_gravada_na_campanha(self):
        campanha = self.mesa()
        enviar_lembretes(agora=AGORA)
        campanha.reload()
        self.assertEqual(campanha.lembrete_enviado_para, AGORA + EM(hours=5))

    def test_sessao_remarcada_e_lembrada_de_novo(self):
        campanha = self.mesa()
        enviar_lembretes(agora=AGORA)
        campanha.data_sessao = AGORA + EM(hours=10)
        campanha.save()
        lembradas = enviar_lembretes(agora=AGORA + EM(minutes=30))
        self.assertEqual(len(lembradas), 1)
        self.assertEqual(len(self.textos_das_notificacoes(self.ana)), 2)

    def test_duas_chamadas_que_se_cruzam_avisam_uma_so_vez(self):
        """Se outra chamada reservou a sessão primeiro, esta não avisa."""
        self.mesa()
        with mock.patch("mongoengine.queryset.base.BaseQuerySet.update_one", return_value=0):
            self.assertEqual(enviar_lembretes(agora=AGORA), [])
        self.assertEqual(self.total_de_avisos(), 0)

    def test_campanha_que_se_repete_e_lembrada_a_cada_sessao(self):
        # Começou há 14 dias, 3 horas depois de "agora": toda semana, no mesmo horário.
        self.mesa(
            recorrencia="semanal",
            data_sessao=AGORA - EM(days=14) + EM(hours=3),
            fuso_mestre="America/Bahia",
        )
        self.assertEqual(len(enviar_lembretes(agora=AGORA)), 1)
        self.assertEqual(enviar_lembretes(agora=AGORA + EM(hours=1)), [])

        # Uma semana depois, a sessão seguinte tem o seu próprio lembrete.
        semana_seguinte = AGORA + EM(days=7)
        self.assertEqual(len(enviar_lembretes(agora=semana_seguinte)), 1)
        self.assertEqual(len(self.textos_das_notificacoes(self.ana)), 2)

    def test_campanha_que_se_repete_nao_e_lembrada_fora_da_janela(self):
        self.mesa(
            recorrencia="semanal",
            data_sessao=AGORA - EM(days=14) + EM(hours=3),
            fuso_mestre="America/Bahia",
        )
        # Três dias depois a próxima sessão ainda está a 4 dias.
        self.assertEqual(enviar_lembretes(agora=AGORA + EM(days=3)), [])


class SimularTests(BaseLembrete):
    def test_simular_lista_sem_avisar_nem_gravar(self):
        campanha = self.mesa()
        lembradas = enviar_lembretes(agora=AGORA, simular=True)
        self.assertEqual([(i["titulo"], i["avisos"]) for i in lembradas], [("A Maldição de Strahd", 3)])
        self.assertEqual(self.total_de_avisos(), 0)
        campanha.reload()
        self.assertIsNone(campanha.lembrete_enviado_para)
        # E depois dá para enviar de verdade.
        self.assertEqual(len(enviar_lembretes(agora=AGORA)), 1)


class FusoDeCadaPessoaTests(BaseLembrete):
    def test_o_horario_vem_no_fuso_de_quem_recebe(self):
        nova_york = self.criar_usuario("nova", fuso_horario="America/New_York")
        agora = datetime.datetime(2026, 11, 30, 20, 0)
        self.mesa(
            data_sessao=datetime.datetime(2026, 12, 1, 0, 0),  # 00:00 UTC
            jogadores_inscritos_emails=[nova_york.email],
        )
        enviar_lembretes(agora=agora)
        self.assertIn(
            "30/11/2026 às 21:00 (Salvador, Bahia)", self.textos_das_notificacoes(self.mestre)[0]
        )
        self.assertIn("30/11/2026 às 19:00 (Nova York)", self.textos_das_notificacoes(nova_york)[0])

    def test_fuso_desconhecido_cai_no_padrao_sem_quebrar(self):
        esquisita = self.criar_usuario("esquisita", fuso_horario="Marte/Olympus")
        self.mesa(jogadores_inscritos_emails=[esquisita.email])
        enviar_lembretes(agora=AGORA)
        self.assertIn("14:00 (Salvador, Bahia)", self.textos_das_notificacoes(esquisita)[0])


@override_settings(LEMBRETES_TOKEN="segredo-de-teste")
class EnderecoDoAgendadorTests(BaseLembrete):
    URL = "/notificacoes/lembretes/"
    CABECALHO = {"HTTP_AUTHORIZATION": "Bearer segredo-de-teste"}

    def mesa_proxima(self):
        return self.mesa(data_sessao=datetime.datetime.utcnow() + EM(hours=3))

    def test_com_o_token_certo_envia_e_responde_o_resumo(self):
        self.mesa_proxima()
        resposta = Client().post(self.URL, **self.CABECALHO)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"campanhas": 1, "avisos": 3})
        self.assertEqual(self.total_de_avisos(), 3)

    def test_chamar_de_novo_nao_repete_os_avisos(self):
        self.mesa_proxima()
        Client().post(self.URL, **self.CABECALHO)
        resposta = Client().post(self.URL, **self.CABECALHO)
        self.assertEqual(resposta.json(), {"campanhas": 0, "avisos": 0})
        self.assertEqual(self.total_de_avisos(), 3)

    def test_sem_o_cabecalho_ou_com_token_errado_recusa(self):
        self.mesa_proxima()
        for extras in ({}, {"HTTP_AUTHORIZATION": "Bearer errado"}, {"HTTP_AUTHORIZATION": "segredo-de-teste"}):
            resposta = Client().post(self.URL, **extras)
            self.assertEqual(resposta.status_code, 403)
        self.assertEqual(self.total_de_avisos(), 0)

    def test_token_com_acentos_nao_derruba_o_endereco(self):
        resposta = Client().post(self.URL, HTTP_AUTHORIZATION="Bearer ação-çã")
        self.assertEqual(resposta.status_code, 403)

    def test_so_aceita_post(self):
        for metodo in ("get", "put", "delete"):
            resposta = getattr(Client(), metodo)(self.URL, **self.CABECALHO)
            self.assertEqual(resposta.status_code, 405)

    def test_funciona_sem_o_token_de_csrf(self):
        self.mesa_proxima()
        resposta = Client(enforce_csrf_checks=True).post(self.URL, **self.CABECALHO)
        self.assertEqual(resposta.status_code, 200)

    @override_settings(LEMBRETES_TOKEN="")
    def test_sem_token_configurado_o_endereco_nao_existe(self):
        self.mesa_proxima()
        # Nem o cabeçalho vazio libera: o recurso está desligado.
        for extras in ({}, {"HTTP_AUTHORIZATION": "Bearer "}):
            resposta = Client().post(self.URL, **extras)
            self.assertEqual(resposta.status_code, 404)
        self.assertEqual(self.total_de_avisos(), 0)


class ComandoTests(BaseLembrete):
    def rodar(self, *args):
        saida = StringIO()
        call_command("enviar_lembretes_sessao", *args, stdout=saida)
        return saida.getvalue()

    def test_envia_e_diz_quantos_lembretes_sairam(self):
        self.mesa(data_sessao=datetime.datetime.utcnow() + EM(hours=3))
        saida = self.rodar()
        self.assertIn("A Maldição de Strahd", saida)
        self.assertIn("3 lembrete(s) de 1 campanha(s) enviados.", saida)
        self.assertEqual(self.total_de_avisos(), 3)

    def test_simular_nao_envia(self):
        self.mesa(data_sessao=datetime.datetime.utcnow() + EM(hours=3))
        saida = self.rodar("--simular")
        self.assertIn("seriam enviados", saida)
        self.assertEqual(self.total_de_avisos(), 0)
        self.assertIsNone(Campanha.objects.first().lembrete_enviado_para)

    def test_horas_muda_a_antecedencia(self):
        self.mesa(data_sessao=datetime.datetime.utcnow() + EM(hours=3))
        self.assertIn("0 lembrete(s) de 0 campanha(s)", self.rodar("--horas", "1"))
        self.assertIn("3 lembrete(s) de 1 campanha(s)", self.rodar("--horas", "6"))

    def test_sem_nada_a_lembrar_diz_zero(self):
        self.assertIn("0 lembrete(s) de 0 campanha(s) enviados.", self.rodar())
