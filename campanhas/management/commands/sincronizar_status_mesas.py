from django.core.management.base import BaseCommand

from campanhas.models import Campanha


class Command(BaseCommand):
    help = (
        "Corrige o status das campanhas gravadas por versões antigas: 'aberta' "
        "sem vaga livre passa a 'lotada' e 'lotada' com vaga passa a 'aberta'."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Só mostra o que mudaria, sem gravar.",
        )

    def handle(self, *args, **opcoes):
        corrigidas = 0
        for campanha in Campanha.objects:
            antigo = campanha.status
            campanha.sincronizar_status()
            if campanha.status == antigo:
                continue
            corrigidas += 1
            self.stdout.write(f'{campanha.titulo}: {antigo} -> {campanha.status}')
            if not opcoes["simular"]:
                # update(): não mexe em `atualizado_em`.
                Campanha.objects(id=campanha.id).update(set__status=campanha.status)

        verbo = "seriam corrigidas" if opcoes["simular"] else "corrigidas"
        self.stdout.write(self.style.SUCCESS(f"{corrigidas} campanha(s) {verbo}."))
