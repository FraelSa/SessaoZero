"""
Como Usuario é um Document do MongoEngine, ele não se conecta sozinho ao
sistema de autenticação do Django (que espera um models.Model relacional).
Em vez de escrever um backend de autenticação customizado, mantemos a
sessão de forma simples e explícita: guardamos o id do Usuario logado em
request.session["usuario_id"] e usamos as funções abaixo para ler/gravar
isso. É pouco código e fácil de entender/explicar na defesa do TCC.
"""

from functools import wraps

from django.shortcuts import redirect
from django.contrib import messages
from mongoengine.errors import ValidationError as MongoValidationError

from .models import Usuario

CHAVE_SESSAO = "usuario_id"

# O Usuario da requisição é buscado uma vez e guardado no próprio `request`:
# o middleware de fuso horário, os context processors e a view o consultam.
_ATRIBUTO_CACHE = "_usuario_sessao_zero"
_SEM_CACHE = object()


def fazer_login(request, usuario):
    request.session[CHAVE_SESSAO] = str(usuario.id)
    request.__dict__.pop(_ATRIBUTO_CACHE, None)


def fazer_logout(request):
    request.session.pop(CHAVE_SESSAO, None)
    request.__dict__.pop(_ATRIBUTO_CACHE, None)


def usuario_atual(request):
    """Retorna o Usuario logado (documento do Mongo) ou None.

    Importante: esta função roda em praticamente toda requisição (é usada
    pelos context processors de accounts e notificacoes), então precisa
    ser resistente a um id de sessão corrompido/antigo/malformado — sem
    o try/except, um único cookie de sessão inválido derrubaria todas as
    páginas do site com erro 500."""
    em_cache = request.__dict__.get(_ATRIBUTO_CACHE, _SEM_CACHE)
    if em_cache is not _SEM_CACHE:
        return em_cache

    usuario = None
    usuario_id = request.session.get(CHAVE_SESSAO)
    if usuario_id:
        try:
            usuario = Usuario.objects(
                id=usuario_id, ativo=True, aguardando_confirmacao__ne=True
            ).first()
        except MongoValidationError:
            # Id em formato inválido: trata como se não houvesse ninguém
            # logado e limpa a sessão para não repetir o erro a cada request.
            request.session.pop(CHAVE_SESSAO, None)
            usuario = None

    request.__dict__[_ATRIBUTO_CACHE] = usuario
    return usuario


def login_obrigatorio(view_func):
    """Decorator equivalente ao @login_required do Django, mas para o nosso
    esquema de sessão baseado em Usuario (Mongo)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if usuario_atual(request) is None:
            messages.info(request, "Você precisa entrar na sua conta para continuar.")
            return redirect("login")
        return view_func(request, *args, **kwargs)

    return wrapper
