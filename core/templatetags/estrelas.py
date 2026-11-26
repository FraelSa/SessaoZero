import math

from django import template
from django.utils.html import format_html

register = template.Library()


def _br(media):
    """4.5 -> '4,5'"""
    return f"{media:.1f}".replace(".", ",")


@register.filter
def nota_br(media):
    """Uso: {{ reputacao.media|nota_br }} -> '4,5' (vírgula, como no Brasil)."""
    return _br(media) if media is not None else ""


@register.simple_tag
def estrelas(media):
    """Uso: {% estrelas reputacao.media %} -> ★★★★☆ com texto para leitor de tela.
    A nota é arredondada para a estrela inteira mais próxima."""
    if media is None:
        return ""
    cheias = max(0, min(5, math.floor(media + 0.5)))
    return format_html(
        '<span class="estrelas" role="img" aria-label="Nota {} de 5">{}{}</span>',
        _br(media),
        "★" * cheias,
        "☆" * (5 - cheias),
    )
