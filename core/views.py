import logging
import sys

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_safe
from mongoengine.connection import get_db
from pymongo.errors import ConnectionFailure

from accounts.auth_utils import usuario_atual
from campanhas.models import Campanha
from moderacao.permissoes import eh_moderador

from . import politica

logger = logging.getLogger(__name__)


def home(request):
    """Página inicial, com as campanhas abertas mais recentes."""
    try:
        campanhas_recentes = list(
            Campanha.objects(status="aberta").order_by("-criado_em")[:3]
        )
    except Exception:  # noqa: BLE001 - a home não deve cair se o banco estiver fora
        campanhas_recentes = []

    return render(request, "core/home.html", {"campanhas_recentes": campanhas_recentes})


def politica_privacidade(request):
    """RNF03 - Política de Privacidade (pública, sem precisar de login)."""
    return render(
        request,
        "core/privacidade.html",
        {"versao": politica.VERSAO, "contato": settings.CONTATO_PRIVACIDADE},
    )


def status_mongo(request):
    """
    Endpoint de diagnóstico: confirma que a conexão com o MongoDB está
    funcionando e mostra quais coleções já existem no banco.

    Útil durante o desenvolvimento para verificar rapidamente a variável
    MONGO_URI do .env sem precisar abrir o Mongo Compass ou o shell.

    RNF03 - o nome do banco, as coleções e as mensagens de erro (que podem trazer o
    endereço do servidor) não são para qualquer visitante: fora do modo de
    desenvolvimento, só moderadores enxergam esta página; os demais recebem 404.
    """
    if not (settings.DEBUG or eh_moderador(usuario_atual(request))):
        raise Http404("Página não encontrada.")
    try:
        db = get_db()
        colecoes = db.list_collection_names()
        return JsonResponse(
            {
                "conectado": True,
                "banco": db.name,
                "colecoes": colecoes,
            }
        )
    except Exception as erro:  # noqa: BLE001 - queremos mostrar qualquer falha de conexão
        # O texto completo do erro só aparece em desenvolvimento.
        detalhe = str(erro) if settings.DEBUG else type(erro).__name__
        return JsonResponse({"conectado": False, "erro": detalhe}, status=500)


# --------------------------------------------------------------------------
# RNF06 - disponibilidade: saber (e mostrar com educação) quando algo está fora
# --------------------------------------------------------------------------


def _sem_cache(resposta):
    resposta["Cache-Control"] = "no-store"
    return resposta


@require_safe
def saude(request):
    """O processo está de pé e responde? Não consulta o banco, de propósito: é o
    endereço que o Render confere a cada poucos segundos, e ele reinicia o serviço
    quando a resposta falha. Um banco fora do ar não se resolve reiniciando o site
    (o reinício só derrubaria também quem ainda está navegando)."""
    return _sem_cache(JsonResponse({"estado": "ok"}))


@require_safe
def saude_do_banco(request):
    """O site e o banco estão funcionando? Para o monitor de disponibilidade
    externo (ex.: UptimeRobot): 200 se o MongoDB responde, 503 se não. O corpo
    não traz detalhes do erro."""
    try:
        get_db().command("ping")
    except Exception:  # noqa: BLE001 - qualquer falha de conexão conta como "fora"
        logger.warning("Teste de saúde: o MongoDB não respondeu", exc_info=True)
        resposta = JsonResponse({"estado": "fora do ar", "banco": "indisponivel"}, status=503)
        resposta["Retry-After"] = "30"
        return _sem_cache(resposta)
    return _sem_cache(JsonResponse({"estado": "ok", "banco": "ok"}))


def _falha_de_conexao_com_o_banco(erro):
    """True se `erro`, ou algo que o causou, é uma falha de conexão com o MongoDB."""
    visitados = 0
    while erro is not None and visitados < 10:
        if isinstance(erro, ConnectionFailure):
            return True
        erro = erro.__cause__ or erro.__context__
        visitados += 1
    return False


def erro_500(request):
    """Página de erro do servidor (handler500). Os modelos não herdam do
    base.html: ele consulta o banco para montar o menu, e o banco pode ser justamente
    o que falhou. Quando é o MongoDB que não responde, o erro é 503 (indisponível
    por um tempo) em vez de 500, com o aviso de tentar de novo."""
    if _falha_de_conexao_com_o_banco(sys.exc_info()[1]):
        resposta = HttpResponse(render_to_string("503.html"), status=503)
        resposta["Retry-After"] = "30"
        return _sem_cache(resposta)
    return _sem_cache(HttpResponse(render_to_string("500.html"), status=500))
