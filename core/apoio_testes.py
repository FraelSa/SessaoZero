"""Apoio aos testes que precisam ler o settings.py "de verdade", como o servidor faz."""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)


def ler_configuracao(codigo, **ambiente):
    """Roda `codigo` (Python) num processo à parte, com o settings.py carregado a
    partir das variáveis de ambiente dadas, e devolve o JSON que ele imprimir na
    última linha.

    Processo à parte porque o settings.py decide coisas na hora em que é importado
    (modo de produção, conexão com o banco). As variáveis DJANGO_* e MONGO_* do
    ambiente de quem roda os testes não passam para o processo, nem o .env aponta
    para um banco de verdade: MONGO_URI vira o endereço local, que só é aberto
    (e de forma preguiçosa) se o código pedir a conexão."""
    cabecalho = "import json, sys\nsys.path.insert(0, sys.argv[1])\nimport sessao_zero.settings as s\n"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "MONGO_", "REDIS_"))}
    env["MONGO_URI"] = "mongodb://localhost:27017"
    env.update(ambiente)
    resultado = subprocess.run(
        [sys.executable, "-c", cabecalho + codigo, str(RAIZ)],
        capture_output=True,
        text=True,
        env=env,
        cwd=RAIZ,
        timeout=60,
    )
    if resultado.returncode != 0:
        raise AssertionError(resultado.stderr)
    return json.loads(resultado.stdout.strip().splitlines()[-1])
