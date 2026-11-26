from django import template

register = template.Library()


@register.filter
def papel_de(campanha, usuario):
    """Papel da pessoa logada na campanha: "mestre", "jogador" (inscrita) ou
    "" (nenhum, ou ninguém logado). Usado para marcar as fichas."""
    if not usuario:
        return ""
    if usuario.email == campanha.mestre_email:
        return "mestre"
    if usuario.email in campanha.jogadores_inscritos_emails:
        return "jogador"
    return ""
