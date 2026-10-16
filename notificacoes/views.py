from django.shortcuts import redirect, render
from mongoengine.errors import ValidationError as MongoValidationError

from accounts.auth_utils import login_obrigatorio, usuario_atual

from .models import Notificacao


@login_obrigatorio
def listar_notificacoes(request):
    usuario = usuario_atual(request)
    notificacoes = Notificacao.objects(destinatario_email=usuario.email)

    # Abrir a lista já marca tudo como lido — comportamento simples e
    # comum em redes sociais (estilo "sininho").
    notificacoes.filter(lida=False).update(lida=True)

    return render(request, "notificacoes/listar.html", {"notificacoes": notificacoes})


@login_obrigatorio
def ir_para_notificacao(request, notificacao_id):
    """Marca uma notificação específica como lida e redireciona para o
    link relacionado a ela (ex.: a campanha que mudou)."""
    usuario = usuario_atual(request)
    try:
        notificacao = Notificacao.objects(
            id=notificacao_id, destinatario_email=usuario.email
        ).first()
    except MongoValidationError:
        notificacao = None

    if notificacao:
        notificacao.lida = True
        notificacao.save()
        if notificacao.url:
            return redirect(notificacao.url)

    return redirect("listar_notificacoes")
