from django import template

from core.horario import para_horario_local

register = template.Library()


@register.filter
def local(valor):
    """Uso: {{ comentario.criado_em|local|date:"d/m/Y, H:i" }}"""
    return para_horario_local(valor)
