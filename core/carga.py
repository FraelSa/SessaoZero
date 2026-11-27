"""
RNF01 e RNF05 - teste de carga: simula várias pessoas navegando ao mesmo tempo e
mede quanto o site demora para responder (só a biblioteca padrão do Python).

Uso, a partir do seu computador, contra o site já publicado:

    python manage.py teste_de_carga https://seusite.onrender.com --usuarios 200 --duracao 60

O resultado mostra, para cada página, o tempo de resposta mediano e dos 95% mais
rápidos (p95), e avisa quando alguma passa dos 2 segundos pedidos pelo RNF01 ou
quando mais de 1% das requisições falha. Rode contra o endereço público, nunca contra
o site de outra pessoa: é carga de verdade.

Limites deste teste (leia antes de tirar conclusões):
- o tempo medido inclui a rede entre o seu computador e o servidor;
- um computador comum não gera milhares de usuários simultâneos: acima de ~500, o
  gargalo passa a ser a sua máquina, e o resultado deixa de valer. Para 5.000, use uma
  ferramenta distribuída (k6, Locust) ou várias máquinas, apontando para as mesmas páginas;
- no plano gratuito do Render o serviço "dorme" depois de 15 minutos sem acesso, e o
  primeiro acesso demora cerca de um minuto; por isso o teste começa "aquecendo" o
  site e mostra esse tempo à parte.
"""

import concurrent.futures
import http.cookiejar
import math
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

LIMITE_DE_TEMPO_S = 2.0  # RNF01 - qualquer tela em até 2 segundos
LIMITE_DE_ERROS = 0.01  # no máximo 1% das requisições com falha
TEMPO_MAXIMO_POR_REQUISICAO_S = 30

PAGINAS_PUBLICAS = (
    "/",
    "/campanhas/",
    "/campanhas/?q=mesa",
    "/campanhas/?p=2",
    "/privacidade/",
    "/contas/login/",
)
# Páginas de quem está logado: as mais pesadas (recomendação, listas pessoais).
PAGINAS_DE_USUARIO = (
    "/campanhas/recomendadas/",
    "/campanhas/inscricoes/",
    "/campanhas/minhas/",
    "/notificacoes/",
)


@dataclass
class Medida:
    caminho: str
    segundos: float
    status: int  # 0 = nem chegou a haver resposta (rede, tempo esgotado)


def percentil(valores, p):
    """Percentil `p` (0 a 100) pelo método do posto mais próximo."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    posto = max(math.ceil(p / 100 * len(ordenados)), 1)
    return ordenados[posto - 1]


def _falhou(medida):
    return medida.status == 0 or medida.status >= 400


def _estatisticas(medidas, duracao_s):
    tempos = [m.segundos for m in medidas]
    falhas = sum(1 for m in medidas if _falhou(m))
    return {
        "requisicoes": len(medidas),
        "falhas": falhas,
        "taxa_de_falhas": falhas / len(medidas) if medidas else 0.0,
        "p50": percentil(tempos, 50),
        "p95": percentil(tempos, 95),
        "p99": percentil(tempos, 99),
        "maximo": max(tempos) if tempos else 0.0,
        "por_segundo": len(medidas) / duracao_s if duracao_s else 0.0,
    }


def resumir(medidas, duracao_s):
    """{"geral": {...}, "paginas": {caminho: {...}}} a partir das medidas."""
    por_pagina = {}
    for medida in medidas:
        por_pagina.setdefault(medida.caminho, []).append(medida)
    return {
        "geral": _estatisticas(medidas, duracao_s),
        "paginas": {c: _estatisticas(m, duracao_s) for c, m in sorted(por_pagina.items())},
    }


def avaliar(resumo, limite_s=LIMITE_DE_TEMPO_S, limite_de_erros=LIMITE_DE_ERROS):
    """Lista de problemas encontrados (vazia = passou)."""
    problemas = []
    geral = resumo["geral"]
    if geral["requisicoes"] == 0:
        return ["Nenhuma requisição foi concluída."]
    if geral["taxa_de_falhas"] > limite_de_erros:
        problemas.append(
            f"{geral['taxa_de_falhas']:.1%} das requisições falharam (o limite é {limite_de_erros:.0%})."
        )
    for caminho, dados in resumo["paginas"].items():
        if dados["p95"] > limite_s:
            problemas.append(
                f"{caminho}: 95% das respostas levaram até {dados['p95']:.2f} s (o limite é {limite_s:g} s)."
            )
    return problemas


def formatar(resultado):
    """Texto do relatório, pronto para imprimir."""
    resumo = resultado["resumo"]
    geral = resumo["geral"]
    linhas = [
        f"Endereço: {resultado['base']}",
        f"Usuários simultâneos: {resultado['usuarios']}   Duração: {resultado['duracao_s']:g} s"
        + ("   (com login)" if resultado["com_login"] else ""),
    ]
    if resultado.get("partida_a_frio_s") is not None:
        linhas.append(f"Primeiro acesso (partida a frio): {resultado['partida_a_frio_s']:.1f} s")
    if resultado["logins"]:
        linhas.append(
            f"Logins: {resultado['logins']['ok']} feitos, {resultado['logins']['falhas']} com falha"
        )
    linhas += [
        "",
        f"{'Página':34} {'req.':>6} {'falhas':>7} {'mediana':>8} {'p95':>7} {'p99':>7} {'máx.':>7}",
    ]

    def linha(nome, d):
        return (
            f"{nome[:34]:34} {d['requisicoes']:6d} {d['falhas']:7d} "
            f"{d['p50']:7.2f}s {d['p95']:6.2f}s {d['p99']:6.2f}s {d['maximo']:6.2f}s"
        )

    for caminho, dados in resumo["paginas"].items():
        linhas.append(linha(caminho, dados))
    linhas += [
        linha("TOTAL", geral),
        "",
        f"Vazão: {geral['por_segundo']:.1f} requisições por segundo.",
    ]
    problemas = resultado["problemas"]
    if problemas:
        linhas.append("")
        linhas.append("PROBLEMAS:")
        linhas += [f"- {p}" for p in problemas]
    else:
        linhas.append(f"Passou: nenhuma página acima de {LIMITE_DE_TEMPO_S:g} s (p95) e falhas dentro do limite.")
    if resultado["usuarios"] > 500:
        linhas.append(
            "Atenção: com tantos usuários simulados, o seu computador pode ser o gargalo; "
            "confira também o uso de CPU e de rede dele."
        )
    return "\n".join(linhas)


# --------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------


def _abrir(base, caminho, abridor, dados=None, cabecalhos=None, tempo=TEMPO_MAXIMO_POR_REQUISICAO_S):
    """Faz uma requisição e devolve (status, corpo, segundos). Status 0 = falha de rede."""
    requisicao = urllib.request.Request(
        base + caminho,
        data=urllib.parse.urlencode(dados).encode() if dados is not None else None,
        headers=cabecalhos or {},
    )
    inicio = time.perf_counter()
    try:
        with abridor.open(requisicao, timeout=tempo) as resposta:
            corpo = resposta.read()
            status = resposta.status
    except urllib.error.HTTPError as erro:
        corpo, status = b"", erro.code
    except (urllib.error.URLError, TimeoutError, OSError):
        corpo, status = b"", 0
    return status, corpo, time.perf_counter() - inicio


def aquecer(base):
    """Acorda o serviço (no plano gratuito ele dorme) e devolve quanto levou."""
    abridor = urllib.request.build_opener()
    _, _, segundos = _abrir(base, "/saude/", abridor, tempo=120)
    return segundos


def _entrar(base, abridor, email, senha):
    """Faz o login e devolve True se funcionou (a sessão fica no `abridor`)."""
    status, corpo, _ = _abrir(base, "/contas/login/", abridor)
    achado = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', corpo)
    if status != 200 or not achado:
        return False
    status, corpo, _ = _abrir(
        base,
        "/contas/login/",
        abridor,
        dados={"csrfmiddlewaretoken": achado.group(1).decode(), "email": email, "senha": senha},
        cabecalhos={"Referer": base + "/contas/login/", "Origin": base},
    )
    # Quem entra é levado à página inicial; quem erra a senha volta ao formulário.
    return status == 200 and b'name="senha"' not in corpo


def _usuario_virtual(base, fim, pausa_s, subida_s, login, medidas):
    """Uma pessoa navegando até a hora de acabar. Devolve se o login funcionou
    (None quando o teste é sem login)."""
    time.sleep(random.uniform(0, subida_s))
    abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    paginas = list(PAGINAS_PUBLICAS)
    entrou = None
    if login:
        entrou = _entrar(base, abridor, *login)
        if entrou:
            paginas += list(PAGINAS_DE_USUARIO)
    while time.monotonic() < fim:
        caminho = random.choice(paginas)
        status, _, segundos = _abrir(base, caminho, abridor)
        medidas.append(Medida(caminho, segundos, status))  # list.append é seguro entre threads
        time.sleep(random.uniform(0.5, 1.5) * pausa_s)
    return entrou


def executar(base, usuarios=50, duracao_s=30, pausa_s=1.0, subida_s=None, login=None, aquecer_antes=True):
    """Roda o teste e devolve o resultado (dicionário com o resumo e os problemas).

    `login` é (e-mail, senha) de uma conta de teste: cada usuário simulado entra com
    ela e passa a visitar também as páginas de quem está logado."""
    base = base.rstrip("/")
    partida_a_frio = aquecer(base) if aquecer_antes else None
    subida_s = min(duracao_s / 4, 10) if subida_s is None else subida_s

    medidas = []
    inicio = time.monotonic()
    fim = inicio + duracao_s
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(usuarios, 1)) as pool:
        futuros = [
            pool.submit(_usuario_virtual, base, fim, pausa_s, subida_s, login, medidas)
            for _ in range(usuarios)
        ]
        entradas = [futuro.result() for futuro in futuros]
    decorrido = max(time.monotonic() - inicio, 0.001)
    logins = {"ok": entradas.count(True), "falhas": entradas.count(False)}

    resumo = resumir(medidas, decorrido)
    problemas = avaliar(resumo)
    if login and logins["ok"] == 0:
        problemas.append("Nenhum login funcionou: confira o e-mail e a senha da conta de teste.")
    return {
        "base": base,
        "usuarios": usuarios,
        "duracao_s": duracao_s,
        "com_login": bool(login),
        "logins": logins if login else None,
        "partida_a_frio_s": partida_a_frio,
        "resumo": resumo,
        "problemas": problemas,
    }
