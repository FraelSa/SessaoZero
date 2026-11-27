import secrets

from django.conf import settings
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from mongoengine.errors import ValidationError as MongoValidationError

from accounts.auth_utils import login_obrigatorio, usuario_atual

from .lembretes import enviar_lembretes
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


@csrf_exempt
def disparar_lembretes(request):
    """RF08 - endereço que um agendador externo chama de hora em hora para
    enviar os lembretes de sessão (o plano gratuito do Render não tem cron).

    Não usa a sessão do site: a chamada precisa do cabeçalho
    `Authorization: Bearer <LEMBRETES_TOKEN>`. Sem LEMBRETES_TOKEN configurado,
    o endereço finge que não existe."""
    token = settings.LEMBRETES_TOKEN
    if not token:
        raise Http404("Lembretes por agendador não estão ativados.")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    enviado = request.headers.get("Authorization", "").encode()
    esperado = f"Bearer {token}".encode()
    if not secrets.compare_digest(enviado, esperado):
        return JsonResponse({"erro": "Token inválido."}, status=403)

    lembradas = enviar_lembretes()
    return JsonResponse(
        {
            "campanhas": len(lembradas),
            "avisos": sum(item["avisos"] for item in lembradas),
        }
    )
