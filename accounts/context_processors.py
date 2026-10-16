from .auth_utils import usuario_atual


def usuario_logado(request):
    """Disponibiliza `usuario_logado` em todos os templates, parecido com o
    `user` que o Django injeta automaticamente — mas apontando para o
    Usuario do Mongo em vez do model de auth padrão."""
    return {"usuario_logado": usuario_atual(request)}
