from django.core.management.base import BaseCommand, CommandError

from core import carga


class Command(BaseCommand):
    help = (
        "RNF01/RNF05 - simula várias pessoas navegando ao mesmo tempo no site e mede "
        "o tempo de resposta de cada página (limite: 2 segundos). Use contra o site publicado."
    )

    def add_arguments(self, parser):
        parser.add_argument("endereco", help="Endereço do site, ex.: https://seusite.onrender.com")
        parser.add_argument("--usuarios", type=int, default=50, help="Usuários simultâneos (padrão: 50)")
        parser.add_argument("--duracao", type=float, default=30, help="Duração em segundos (padrão: 30)")
        parser.add_argument(
            "--pausa", type=float, default=1.0,
            help="Tempo médio, em segundos, que cada usuário 'lê' entre uma página e outra (padrão: 1)",
        )
        parser.add_argument(
            "--entrar", metavar="EMAIL:SENHA",
            help="Conta de teste: cada usuário entra com ela e visita também as páginas de quem está logado",
        )
        parser.add_argument(
            "--sem-aquecer", action="store_true",
            help="Não acorda o site antes de começar (o primeiro acesso após dormir pode levar um minuto)",
        )

    def handle(self, *args, **opcoes):
        endereco = opcoes["endereco"]
        if not endereco.startswith(("http://", "https://")):
            raise CommandError("O endereço precisa começar com http:// ou https://")
        if opcoes["usuarios"] < 1 or opcoes["duracao"] <= 0:
            raise CommandError("Informe pelo menos 1 usuário e uma duração maior que zero.")

        login = None
        if opcoes["entrar"]:
            email, separador, senha = opcoes["entrar"].partition(":")
            if not separador or not email or not senha:
                raise CommandError("Use --entrar EMAIL:SENHA")
            login = (email, senha)

        self.stdout.write(f"Aquecendo e testando {endereco} ... (leva cerca de {opcoes['duracao']:g} s)")
        resultado = carga.executar(
            endereco,
            usuarios=opcoes["usuarios"],
            duracao_s=opcoes["duracao"],
            pausa_s=opcoes["pausa"],
            login=login,
            aquecer_antes=not opcoes["sem_aquecer"],
        )
        self.stdout.write("\n" + carga.formatar(resultado))
        if resultado["problemas"]:
            raise CommandError("O teste encontrou problemas (veja acima).")
