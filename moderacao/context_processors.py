from accounts.auth_utils import usuario_atual

from .models import ConteudoBloqueado
from .permissoes import eh_moderador


def moderacao_no_menu(request):
    """Para moderadores, mostra no menu o link do painel com a quantidade de
    registros ainda não revisados. Para os outros, não faz nenhuma consulta."""
    if not eh_moderador(usuario_atual(request)):
        return {"eh_moderador": False}
    return {
        "eh_moderador": True,
        "bloqueios_pendentes": ConteudoBloqueado.objects(revisado_em=None).count(),
    }
