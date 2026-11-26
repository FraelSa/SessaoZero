from django import template

from core.horario import deslocamento_utc, para_horario_local

register = template.Library()


@register.filter
def local(valor):
    """Uso: {{ comentario.criado_em|local|date:"d/m/Y, H:i" }}
    Converte a data gravada em UTC para o fuso de quem está vendo a página."""
    return para_horario_local(valor)


@register.filter
def utc_de(valor):
    """Uso: {{ data|local|utc_de }} -> 'UTC-03:00'"""
    return deslocamento_utc(valor) if valor is not None else ""
