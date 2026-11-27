"""
RNF04 - quem pode revisar o conteúdo barrado.

Moderador é quem tem o e-mail listado na variável MODERADORES_EMAILS (separados
por vírgula). Não há cadastro de moderadores no banco: a lista fica com quem
administra o servidor, junto das outras senhas e chaves.
"""

from functools import wraps

from django.conf import settings
from django.http import Http404

from accounts.auth_utils import login_obrigatorio, usuario_atual


def eh_moderador(usuario):
    if usuario is None:
        return False
    return usuario.email.strip().lower() in settings.MODERADORES_EMAILS


def moderador_obrigatorio(view):
    """Como `login_obrigatorio`, e ainda só deixa passar moderadores. Quem não é
    moderador recebe 404, como se a página não existisse."""

    @wraps(view)
    @login_obrigatorio
    def wrapper(request, *args, **kwargs):
        if not eh_moderador(usuario_atual(request)):
            raise Http404("Página não encontrada.")
        return view(request, *args, **kwargs)

    return wrapper
