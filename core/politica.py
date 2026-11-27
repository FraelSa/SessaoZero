"""
RNF03 - Política de Privacidade. Sempre que o texto de
core/templates/core/privacidade.html mudar de verdade, troque a VERSAO: ela é
gravada no cadastro de quem aceita (Usuario.politica_versao).
"""

VERSAO = "2026-11-27"


def prazos():
    """Os prazos e limites que a política anuncia, lidos das mesmas constantes que o
    código usa para cumpri-los: se um deles mudar no código, a página muda junto
    (e, como o texto mudou de verdade, vale trocar a VERSAO)."""
    # Importados aqui para evitar importação circular (accounts.views usa a política).
    from accounts import limite_login
    from moderacao.models import RETENCAO_DIAS as dias_moderacao
    from notificacoes.models import RETENCAO_DIAS as dias_avisos

    return {
        "dias_avisos": dias_avisos,
        "dias_moderacao": dias_moderacao,
        "limite_de_falhas": limite_login.LIMITE_DE_FALHAS,
        "janela_minutos": int(limite_login.JANELA.total_seconds() // 60),
    }
