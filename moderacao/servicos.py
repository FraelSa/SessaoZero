"""
RNF04 - funções que ligam o filtro (filtros.py) aos formulários do site: confere
os textos de um formulário já validado, põe o motivo no campo barrado e guarda o
registro da tentativa para a revisão.
"""

from .models import ConteudoBloqueado

# Quem ainda não tem conta (cadastro) não tem e-mail confirmado: o registro não
# guarda o endereço digitado, que pode ser de outra pessoa.
AUTOR_ANONIMO = "cadastro-anonimo"


def registrar_bloqueio(autor_email, texto, motivo, origem):
    """Guarda a tentativa barrada (texto limitado ao tamanho do registro)."""
    return ConteudoBloqueado.objects.create(
        autor_email=autor_email,
        texto_original=texto[: ConteudoBloqueado.texto_original.max_length],
        motivo=motivo,
        origem=origem,
    )


def moderar_campos(form, autor_email, campos, antigos=None):
    """Confere os textos de `form` (já com `is_valid()` verdadeiro).

    `campos` diz o que conferir: {"nome_do_campo": (origem, função_de_moderação)},
    em que a função devolve (aceito, motivo), como `moderar_texto`. `antigos` tem
    os valores que o objeto já tinha: um texto que não mudou não é conferido de
    novo, para quem edita outra coisa não ser barrado por um texto antigo.

    Devolve True se tudo passou. Senão, cada texto barrado vira um erro no seu
    campo, a tentativa é registrada e o resultado é False."""
    antigos = antigos or {}
    tudo_certo = True
    for nome, (origem, moderar) in campos.items():
        valor = form.cleaned_data.get(nome) or ""
        if not valor or valor == antigos.get(nome):
            continue
        aceito, motivo = moderar(valor)
        if not aceito:
            registrar_bloqueio(autor_email, valor, motivo, origem)
            form.add_error(nome, motivo)
            tudo_certo = False
    return tudo_certo
