from django.http import JsonResponse
from django.shortcuts import render
from mongoengine.connection import get_db

from campanhas.models import Campanha


def home(request):
    """Página inicial, com as campanhas abertas mais recentes."""
    try:
        campanhas_recentes = list(
            Campanha.objects(status="aberta").order_by("-criado_em")[:3]
        )
    except Exception:  # noqa: BLE001 - a home não deve cair se o banco estiver fora
        campanhas_recentes = []

    return render(request, "core/home.html", {"campanhas_recentes": campanhas_recentes})


def status_mongo(request):
    """
    Endpoint de diagnóstico: confirma que a conexão com o MongoDB está
    funcionando e mostra quais coleções já existem no banco.

    Útil durante o desenvolvimento para verificar rapidamente a variável
    MONGO_URI do .env sem precisar abrir o Mongo Compass ou o shell.
    """
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
        return JsonResponse({"conectado": False, "erro": str(erro)}, status=500)
