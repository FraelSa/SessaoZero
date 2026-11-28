"""
RNF02 / RNF03 - links enviados por e-mail (confirmar cadastro, redefinir a senha,
trocar o e-mail) levam um código secreto. Quem tem o código entra na conta, então
o banco guarda só um resumo irreversível dele (SHA-256): se o banco vazar, os
resumos não servem para abrir os links. O código em si só existe no e-mail.

O código é aleatório e longo (256 bits), então um SHA-256 simples basta; o
algoritmo lento das senhas só é necessário para segredos que uma pessoa escolhe.
"""

import hashlib
import secrets


def resumo_do_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def gerar_token():
    """Devolve (token, resumo): o token vai no link do e-mail; só o resumo é
    gravado no banco."""
    token = secrets.token_urlsafe(32)
    return token, resumo_do_token(token)
