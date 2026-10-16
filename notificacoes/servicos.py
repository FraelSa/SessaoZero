"""
Ponto único usado pelos outros apps (por enquanto, campanhas) para criar
notificações. Cada notificação é salva no banco (aparece no sininho do
site) e, se o usuário não tiver desligado a opção em Preferências, também é
enviada por e-mail.
"""

import logging
import threading

from django.conf import settings
from django.core.mail import send_mail

from accounts.models import Usuario

from .models import Notificacao

logger = logging.getLogger(__name__)


def _enviar_email(destinatario_email, texto, url):
    link = settings.SITE_URL.rstrip("/") + (url or "")
    try:
        send_mail(
            subject="Sessão Zero - você tem uma notificação",
            message=(
                f"{texto}\n\n"
                f"Veja na Sessão Zero: {link}\n\n"
                "Para parar de receber e-mails como este, desmarque a opção "
                "\"Receber avisos por e-mail\" em Preferências."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[destinatario_email],
        )
    except Exception:  # noqa: BLE001
        # Falha de e-mail (SMTP fora do ar, senha errada...) nunca deve
        # impedir a ação que gerou a notificação; fica só no log.
        logger.exception("Falha ao enviar e-mail de notificação para %s", destinatario_email)


def notificar(destinatario_email, texto, url=""):
    if not destinatario_email:
        return None

    notificacao = Notificacao.objects.create(
        destinatario_email=destinatario_email, texto=texto, url=url
    )

    usuario = Usuario.objects(email=destinatario_email, ativo=True).first()
    if usuario and usuario.notificar_por_email and not usuario.aguardando_confirmacao:
        # Em segundo plano, para a página não esperar o servidor de e-mail.
        threading.Thread(
            target=_enviar_email, args=(usuario.email, texto, url), daemon=True
        ).start()

    return notificacao


def notificar_varios(destinatarios_email, texto, url=""):
    """Atalho para mandar a mesma notificação para uma lista de e-mails
    (ex.: todos os jogadores inscritos numa campanha)."""
    for email in destinatarios_email:
        notificar(email, texto, url=url)
