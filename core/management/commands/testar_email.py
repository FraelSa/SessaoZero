import smtplib

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envia um e-mail de teste com as configurações atuais do .env."

    def add_arguments(self, parser):
        parser.add_argument("destino", help="E-mail que vai receber o teste")

    def handle(self, *args, **opcoes):
        destino = opcoes["destino"]
        self.stdout.write(f"Backend:   {settings.EMAIL_BACKEND}")
        self.stdout.write(f"Servidor:  {settings.EMAIL_HOST or '(não definido)'}:{settings.EMAIL_PORT}")
        self.stdout.write(f"Usuário:   {settings.EMAIL_HOST_USER or '(não definido)'}")
        self.stdout.write(f"Remetente: {settings.DEFAULT_FROM_EMAIL}")

        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            self.stdout.write(self.style.WARNING(
                "\nO backend é o do terminal: o e-mail só vai aparecer logo abaixo, "
                "não chega a nenhuma caixa de entrada. Veja o .env.example para configurar o SMTP.\n"
            ))

        try:
            send_mail(
                subject="Sessão Zero - teste de e-mail",
                message="Se você recebeu esta mensagem, o envio de e-mails da Sessão Zero está funcionando.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[destino],
            )
        except smtplib.SMTPAuthenticationError:
            raise CommandError(
                "O servidor recusou o usuário ou a senha. No Gmail, use uma "
                "\"senha de app\" (a senha normal da conta não funciona)."
            )
        except (smtplib.SMTPException, OSError) as erro:
            raise CommandError(f"Falha ao enviar: {erro}")

        self.stdout.write(self.style.SUCCESS(f"Pronto: e-mail enviado para {destino}."))
