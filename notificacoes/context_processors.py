from accounts.auth_utils import usuario_atual

from .models import Notificacao


def notificacoes_nao_lidas(request):
    """Disponibiliza `total_notificacoes_nao_lidas` em todos os templates,
    para mostrar um contador tipo "sininho" no menu."""
    usuario = usuario_atual(request)
    if not usuario:
        return {"total_notificacoes_nao_lidas": 0}

    total = Notificacao.objects(destinatario_email=usuario.email, lida=False).count()
    return {"total_notificacoes_nao_lidas": total}
