import os

from django.contrib.staticfiles import finders

_caminho_css = None


def versao_css(request):
    """Número que muda toda vez que o arquivo de estilo é alterado. Usado na
    URL do CSS (?v=...) para o navegador nunca mostrar a versão antiga."""
    global _caminho_css
    if _caminho_css is None:
        _caminho_css = finders.find("core/css/sessao_zero.css") or ""
    try:
        versao = int(os.path.getmtime(_caminho_css))
    except OSError:
        versao = 0
    return {"versao_css": versao}
