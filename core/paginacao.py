"""
RNF01 / RNF05 - listas que podem crescer sem limite (campanhas, notificações,
registros da moderação) são mostradas em páginas, para o tempo de resposta e o
tamanho da página não aumentarem junto com o banco.
"""

from django.core.paginator import Paginator


def paginar(request, consulta, por_pagina):
    """Devolve (pagina, parametros): a página pedida em `?p=` (uma inválida vira a
    primeira, uma além do fim vira a última) e os outros parâmetros da consulta
    já prontos para os links ("q=strahd&"), para o botão de página não perdê-los."""
    pagina = Paginator(consulta, por_pagina).get_page(request.GET.get("p"))

    outros = request.GET.copy()
    outros.pop("p", None)
    parametros = outros.urlencode()
    return pagina, (parametros + "&" if parametros else "")
