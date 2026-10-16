"""
Avatares do perfil. Cada pessoa pode ter:
  1. uma foto enviada por ela (guardada em FotoPerfil, ver models.py);
  2. um avatar pronto, de tema RPG (os SVGs em accounts/static/accounts/avatares/);
  3. nada escolhido: aí o site desenha um círculo colorido com a inicial do nome.

Este módulo não depende do Django, para ser fácil de testar sozinho.
"""

from xml.sax.saxutils import escape

# (id do arquivo SVG, nome mostrado na tela)
AVATARES_PRONTOS = (
    ("dado", "Dado d20"),
    ("guerreiro", "Guerreiro"),
    ("paladino", "Paladino"),
    ("mago", "Mago"),
    ("arqueiro", "Arqueiro"),
    ("bardo", "Bardo"),
    ("ladino", "Ladino"),
    ("clerigo", "Clérigo"),
)
IDS_AVATARES_PRONTOS = tuple(i for i, _ in AVATARES_PRONTOS)

_CORES_INICIAIS = (
    "#3b3fd6", "#0f766e", "#b45309", "#6d28d9",
    "#b3261e", "#17653f", "#334155", "#a16207",
)


def svg_iniciais(username):
    """Círculo colorido com a primeira letra do nome. A cor é sempre a
    mesma para o mesmo nome."""
    nome = (username or "").strip()
    inicial = escape((nome[:1] or "?").upper())
    cor = _CORES_INICIAIS[sum(nome.encode("utf-8")) % len(_CORES_INICIAIS)]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
        f'<circle cx="48" cy="48" r="48" fill="{cor}"/>'
        '<text x="48" y="48" dy="0.35em" text-anchor="middle" '
        'font-family="Arial, Helvetica, sans-serif" font-size="44" '
        f'font-weight="700" fill="#fff">{inicial}</text></svg>'
    )
