from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.auth_utils import login_obrigatorio, usuario_atual
from campanhas.utils import buscar_campanha_ou_404

from .models import MensagemChat

LIMITE_HISTORICO = 100


@login_obrigatorio
def sala_chat(request, campanha_id):
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)

    eh_participante = usuario.email == campanha.mestre_email or (
        usuario.email in campanha.jogadores_inscritos_emails
    )
    if not eh_participante:
        messages.error(
            request, "Só o mestre e os jogadores inscritos podem acessar o chat da campanha."
        )
        return redirect("detalhe_campanha", campanha_id=campanha.id)

    historico = MensagemChat.objects(campanha_id=str(campanha.id)).order_by("-criado_em")[
        :LIMITE_HISTORICO
    ]
    historico = list(reversed(historico))

    return render(
        request,
        "chat/sala.html",
        {"campanha": campanha, "historico": historico, "usuario": usuario},
    )
