"""
RNF04 - moderação em tempo real do conteúdo enviado por usuários: chat,
comentários, avaliações, biografia, título e sinopse das campanhas e nomes de
usuário.

É uma implementação por palavras-chave e alguns padrões (spam de links, texto
todo em caixa alta), pensada para o escopo do TCC. Os termos ficam em
moderacao/termos_proibidos.txt, para quem cuida da comunidade ajustar a lista
sem mexer em código. O filtro:

- compara palavras inteiras ("burro" não barra "aburrido");
- ignora maiúsculas, acentos e letras repetidas ("iiidiota");
- enxerga números e símbolos no lugar de letras ("1d10t4", "@rrombado");
- enxerga letras separadas ("i d i o t a", "i.d.i.o.t.a");
- aceita usos legítimos listados em EXCECOES ("burro de carga").

Nada disso substitui um modelo que entenda o contexto. Para uma comunidade
grande, o recomendado é manter a lista curada por pessoas e/ou usar um serviço
especializado em toxicidade (por exemplo, a Perspective API do Google). O resto
do sistema só depende de `moderar_texto` e `moderar_nome`, então trocar a
implementação não exige mudar chat/, campanhas/ nem accounts/.
"""

import functools
import re
import unicodedata
from pathlib import Path

ARQUIVO_TERMOS = Path(__file__).with_name("termos_proibidos.txt")

# Usada só se o arquivo de termos não puder ser lido: o filtro nunca fica sem lista.
_TERMOS_DE_EMERGENCIA = ("idiota", "imbecil", "burro")

# Frases legítimas que contêm um termo da lista (sem acento e em minúsculas).
EXCECOES = (
    "burro de carga",
    "burros de carga",
)

PADRAO_LINK = re.compile(r"https?://")

MAX_LINKS_TEXTO = 1
MAX_LINKS_SINOPSE = 3

# Número ou símbolo usado no lugar de uma letra.
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)
_PALAVRA = re.compile(r"[a-z0-9@$]+")
# Três ou mais letras soltas, separadas por espaço ou pontuação: "i d i o t a".
_LETRAS_SOLTAS = re.compile(r"(?<![a-z0-9])(?:[a-z][\s.\-_*]+){2,}[a-z](?![a-z0-9])")
_SEPARADORES = re.compile(r"[\s.\-_*]+")


def normalizar(texto, leet=False):
    """Texto em minúsculas, sem acento e com as letras soltas juntadas. Com
    `leet=True`, os números e símbolos usados no lugar de letras ("1d10t4") são
    trocados por elas. Serve só para comparar; nunca é mostrado nem gravado."""
    decomposto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in decomposto if not unicodedata.combining(c)).lower()

    if leet:

        def destravar(achado):
            palavra = achado.group()
            # Só palavras que têm alguma letra: "2000" continua sendo 2000.
            return palavra.translate(_LEET) if any(c.isalpha() for c in palavra) else palavra

        texto = _PALAVRA.sub(destravar, texto)
    return _LETRAS_SOLTAS.sub(lambda achado: _SEPARADORES.sub("", achado.group()), texto)


def _formas(termo):
    """O termo e suas formas comuns: plural, feminino e plural do feminino."""
    if " " in termo:
        return {termo}
    formas = {termo, termo + "s"}
    if termo.endswith("o"):
        formas |= {termo[:-1] + "a", termo[:-1] + "as", termo[:-1] + "os"}
    elif termo.endswith("a"):
        formas |= {termo[:-1] + "o", termo[:-1] + "os"}
    elif termo.endswith("il"):
        formas.add(termo[:-2] + "is")  # imbecil -> imbecis
    elif termo.endswith("l"):
        formas.add(termo[:-1] + "is")  # animal -> animais
    return formas


def _padrao_da_forma(forma):
    """Cada letra pode se repetir ("idiiiota"); espaços casam com qualquer espaço."""
    palavras = ("".join(re.escape(letra) + "+" for letra in palavra) for palavra in forma.split())
    return r"\s+".join(palavras)


def _compilar(termos):
    formas = set()
    for termo in termos:
        formas |= _formas(termo)
    if not formas:
        return None
    padroes = sorted((_padrao_da_forma(forma) for forma in formas), key=len, reverse=True)
    return re.compile(r"(?<![a-z])(?:" + "|".join(padroes) + r")(?![a-z])")


def ler_termos(arquivo=ARQUIVO_TERMOS):
    """Termos do arquivo, já normalizados. Sem o arquivo, usa a lista de emergência."""
    try:
        linhas = Path(arquivo).read_text(encoding="utf-8").splitlines()
    except OSError:
        return list(_TERMOS_DE_EMERGENCIA)
    termos = []
    for linha in linhas:
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            termos.append(" ".join(normalizar(linha).split()))
    return termos


@functools.lru_cache(maxsize=1)
def _regex_dos_termos():
    return _compilar(ler_termos())


@functools.lru_cache(maxsize=1)
def _regex_das_excecoes():
    return re.compile(
        r"(?<![a-z])(?:" + "|".join(_padrao_da_forma(frase) for frase in EXCECOES) + r")(?![a-z])"
    )


def _contem_termo_proibido(texto):
    regex = _regex_dos_termos()
    if regex is None:
        return False
    # Duas leituras: a normal ("idiota123" tem o termo, e o número não vira
    # letra) e a que troca números por letras ("1d10t4").
    for leet in (False, True):
        sem_excecoes = _regex_das_excecoes().sub(" ", normalizar(texto, leet=leet))
        if regex.search(sem_excecoes):
            return True
    return False


def _eh_grito(texto):
    """Texto digitado quase todo em caixa alta - geralmente é grosseria
    ou spam chamando atenção."""
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 8:
        return False
    proporcao_maiusculas = sum(1 for c in letras if c.isupper()) / len(letras)
    return proporcao_maiusculas > 0.7


def _eh_spam_de_links(texto, max_links=MAX_LINKS_TEXTO):
    return len(PADRAO_LINK.findall(texto)) > max_links


def moderar_texto(texto, max_links=MAX_LINKS_TEXTO):
    """
    Verifica um texto (mensagem de chat, comentário, biografia...) antes de ele
    ser salvo ou distribuído aos outros usuários.

    Retorna uma tupla (aceito: bool, motivo: str). Quando aceito é False,
    `motivo` é uma mensagem pronta para mostrar a quem tentou enviar o conteúdo.
    """
    if _contem_termo_proibido(texto):
        return False, "Sua mensagem contém um termo não permitido na Sessão Zero."

    if _eh_grito(texto):
        return False, "Evite escrever tudo em maiúsculas — parece grosseria."

    if _eh_spam_de_links(texto, max_links):
        return False, "Muitos links em uma única mensagem — parece spam."

    return True, ""


def moderar_sinopse(texto):
    """Como `moderar_texto`, mas a sinopse de uma campanha pode ter mais links
    (convite do Discord, mesa virtual, ficha)."""
    return moderar_texto(texto, max_links=MAX_LINKS_SINOPSE)


def moderar_nome(texto):
    """Para textos curtos que identificam algo (nome de usuário, título da
    campanha, nome de um sistema): só confere os termos. Maiúsculas são comuns
    nesses campos ("D&D", "CALL OF CTHULHU") e não indicam grosseria."""
    if _contem_termo_proibido(texto):
        return False, "Esse texto contém um termo não permitido na Sessão Zero."
    return True, ""
