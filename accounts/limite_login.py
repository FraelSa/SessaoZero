"""
RNF02 / RNF03 - limite de tentativas de senha errada.

Sem limite, dá para testar milhares de senhas por minuto contra um e-mail. Aqui,
depois de LIMITE_DE_FALHAS senhas erradas para o mesmo e-mail em JANELA, novas
tentativas são recusadas até as mais antigas saírem da janela, sem sequer
calcular o hash da senha (o que também poupa o servidor).

A conta é identificada só pelo e-mail digitado, de propósito: o endereço de IP
que o servidor enxerga atrás do proxy do Render pode ser forjado por quem
controla o cabeçalho X-Forwarded-For, e um limite por IP daria falsa segurança.
Existindo ou não a conta, o limite funciona do mesmo jeito, para não revelar
quais e-mails estão cadastrados. Quem for travado por engano (ou por alguém mal
intencionado) ainda pode redefinir a senha por e-mail.

Não protege contra quem tenta uma senha comum em muitos e-mails diferentes; é
por isso que o cadastro recusa senhas comuns (AUTH_PASSWORD_VALIDATORS).
"""

import datetime
import hashlib
import math

from .models import TentativaLogin

LIMITE_DE_FALHAS = 5
JANELA = datetime.timedelta(minutes=15)


class TentativasEsgotadas(Exception):
    """Levantada quando o e-mail já errou a senha vezes demais. A mensagem está
    pronta para mostrar à pessoa."""

    def __init__(self, minutos):
        self.minutos = minutos
        unidade = "minuto" if minutos == 1 else "minutos"
        super().__init__(
            f"Muitas tentativas com senha errada. Por segurança, aguarde {minutos} "
            f"{unidade} para tentar de novo, ou use “Esqueci minha senha”."
        )


def _chave(email):
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def verificar(email, agora=None):
    """Levanta TentativasEsgotadas se o e-mail está travado."""
    agora = agora or datetime.datetime.utcnow()
    falhas = list(
        TentativaLogin.objects(chave=_chave(email), quando__gt=agora - JANELA)
        .order_by("quando")
        .only("quando")
    )
    if len(falhas) >= LIMITE_DE_FALHAS:
        # Libera quando a falha que deixa a conta no limite sai da janela.
        libera_em = falhas[len(falhas) - LIMITE_DE_FALHAS].quando + JANELA
        raise TentativasEsgotadas(max(math.ceil((libera_em - agora).total_seconds() / 60), 1))


def registrar_falha(email, agora=None):
    TentativaLogin(chave=_chave(email), quando=agora or datetime.datetime.utcnow()).save()


def limpar(email):
    """Quem acerta a senha volta a ter todas as tentativas."""
    TentativaLogin.objects(chave=_chave(email)).delete()


def conferir_senha(usuario, senha):
    """Confere a senha de um usuário respeitando o limite: True se confere,
    False se não; levanta TentativasEsgotadas se o e-mail está travado."""
    verificar(usuario.email)
    if usuario.checar_senha(senha):
        limpar(usuario.email)
        return True
    registrar_falha(usuario.email)
    return False
