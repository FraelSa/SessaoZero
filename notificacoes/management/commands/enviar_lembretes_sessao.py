import datetime

from django.core.management.base import BaseCommand

from core.horario import para_horario_local
from notificacoes.lembretes import ANTECEDENCIA, enviar_lembretes


class Command(BaseCommand):
    help = (
        "RF08 - envia o lembrete de sessão (mestre e jogadores inscritos) das "
        "campanhas cuja próxima sessão começa nas próximas horas. Pode rodar "
        "quantas vezes quiser: cada sessão é lembrada uma vez só. Pensado para "
        "um agendador chamar de hora em hora."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--horas",
            type=int,
            default=int(ANTECEDENCIA.total_seconds() // 3600),
            help="Com quantas horas de antecedência avisar (padrão: 24).",
        )
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Só mostra quem seria avisado, sem avisar nem gravar.",
        )

    def handle(self, *args, **opcoes):
        lembradas = enviar_lembretes(
            antecedencia=datetime.timedelta(hours=opcoes["horas"]),
            simular=opcoes["simular"],
            # O comando termina logo depois de avisar: os e-mails saem antes disso.
            em_segundo_plano=False,
        )
        for item in lembradas:
            quando = para_horario_local(item["sessao"])
            self.stdout.write(f'{item["titulo"]}: {quando:%d/%m/%Y %H:%M}, {item["avisos"]} pessoa(s)')

        total = sum(item["avisos"] for item in lembradas)
        verbo = "seriam enviados" if opcoes["simular"] else "enviados"
        self.stdout.write(
            self.style.SUCCESS(
                f"{total} lembrete(s) de {len(lembradas)} campanha(s) {verbo}."
            )
        )
