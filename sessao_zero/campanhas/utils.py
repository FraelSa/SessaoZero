from django.http import Http404
from mongoengine.errors import ValidationError as MongoValidationError

from .models import Campanha


def buscar_campanha_ou_404(campanha_id):
    """Equivalente ao get_object_or_404 do Django, mas para Document do
    MongoEngine: um id em formato inválido levanta ValidationError em vez
    de simplesmente não achar nada, então tratamos os dois casos aqui."""
    try:
        campanha = Campanha.objects(id=campanha_id).first()
    except MongoValidationError:
        campanha = None
    if campanha is None:
        raise Http404("Campanha não encontrada.")
    return campanha
