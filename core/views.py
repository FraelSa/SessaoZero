from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from mongoengine.connection import get_db

from accounts.auth_utils import usuario_atual
from campanhas.models import Campanha
from moderacao.permissoes import eh_moderador

from . import politica


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
