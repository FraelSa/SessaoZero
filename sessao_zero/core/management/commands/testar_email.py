import smtplib

from anymail.exceptions import AnymailError
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
        if settings.EMAIL_BACKEND.startswith("anymail."):
            self.stdout.write("Servidor:  API da Brevo (BREVO_API_KEY)")
        else:
            self.stdout.write(f"Servidor:  {settings.EMAIL_HOST or '(não definido)'}:{settings.EMAIL_PORT}")
            self.stdout.write(f"Usuário:   {settings.EMAIL_HOST_USER or '(não definido)'}")
        self.stdout.write(f"Remetente: {settings.DEFAULT_FROM_EMAIL}")

        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            self.stdout.write(self.style.WARNING(
                "\nO backend é o do terminal: o e-mail só vai aparecer logo abaixo, "
                "não chega a nenhuma caixa de entrada. Configure o SMTP ou a "
                "BREVO_API_KEY no .env para enviar de verdade.\n"
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
        except AnymailError as erro:
            raise CommandError(
                f"A Brevo recusou o envio: {erro}\n"
                "Confira se a BREVO_API_KEY é uma chave de API (não a chave SMTP) "
                "e se o DEFAULT_FROM_EMAIL usa o domínio autenticado na Brevo."
            )

        self.stdout.write(self.style.SUCCESS(f"Pronto: e-mail enviado para {destino}."))
