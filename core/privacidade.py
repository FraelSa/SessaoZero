"""
RNF03 - ajudas para não deixar dados pessoais onde não precisam estar.
"""


def mascarar_email(email):
    """'ana.silva@exemplo.com' vira 'a***@exemplo.com': serve para os registros de
    erro (logs), que ficam fora do controle da pessoa e não precisam do endereço
    inteiro para o erro ser entendido."""
    nome, arroba, dominio = (email or "").partition("@")
    if not arroba:
        return "***"
    return f"{nome[:1]}***@{dominio}"
