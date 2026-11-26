from django.utils import timezone

from accounts.auth_utils import usuario_atual

from .horario import FUSO_PADRAO, zona_segura


class FusoHorarioMiddleware:
    """Ativa, a cada requisição, o fuso horário da pessoa logada (escolhido em
    Preferências). Sem login, vale o fuso padrão (America/Bahia). Com o fuso
    ativo, datas em UTC são convertidas na hora de exibir e o horário digitado
    em formulários é interpretado nesse fuso (ver core/horario.py)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = usuario_atual(request)
        nome = (usuario.fuso_horario if usuario is not None else None) or FUSO_PADRAO
        timezone.activate(zona_segura(nome))
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
