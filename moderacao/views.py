"""
RNF04 - painel para revisar o conteúdo que o filtro barrou. Só moderadores
(ver permissoes.py) chegam aqui. A revisão serve para ajustar a lista de termos:
um bloqueio marcado como falso positivo mostra um termo ou uma regra que está
barrando gente à toa; um repetido pela mesma pessoa mostra quem insiste.
"""

import collections
import datetime

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from mongoengine.errors import ValidationError as MongoValidationError

from accounts.auth_utils import usuario_atual
from core.paginacao import paginar

from .models import RETENCAO_DIAS, ConteudoBloqueado
from .permissoes import moderador_obrigatorio

POR_PAGINA = 25
# Quem foi barrado pelo menos REINCIDENCIA_MIN vezes nos últimos REINCIDENCIA_DIAS
# dias aparece em destaque.
REINCIDENCIA_MIN = 3
REINCIDENCIA_DIAS = 7

ESTADOS = (
    ("pendentes", "Ainda não revisados"),
    ("revisados", "Já revisados"),
    ("todos", "Todos"),
)

# O que vem antes dos dois-pontos na origem do registro ("chat:<id>").
ORIGENS = (
    ("", "Todas as origens"),
    ("chat", "Chat"),
    ("comentario", "Comentários"),
    ("avaliacao", "Avaliações"),
    ("perfil", "Perfil (biografia e nome)"),
    ("campanha", "Campanhas (título, sinopse, sistema)"),
    ("cadastro", "Cadastro"),
)

ROTULOS_DE_ORIGEM = {
    "chat": "Chat",
    "comentario": "Comentário",
    "avaliacao": "Avaliação",
    "perfil:bio": "Biografia",
    "perfil:usuario": "Nome de usuário (troca)",
    "campanha:titulo": "Título da campanha",
    "campanha:sinopse": "Sinopse da campanha",
    "campanha:sistema": "Sistema da campanha",
    "cadastro:usuario": "Nome de usuário (cadastro)",
}

DECISOES_ACEITAS = ("correto", "falso_positivo", "pendente")


def rotulo_da_origem(origem):
    """'chat:65f...' vira 'Chat'; origens que o painel não conhece aparecem como estão."""
    return ROTULOS_DE_ORIGEM.get(origem) or ROTULOS_DE_ORIGEM.get(origem.split(":")[0], origem)


def _reincidentes(agora):
    desde = agora - datetime.timedelta(days=REINCIDENCIA_DIAS)
    contagem = collections.Counter(
        bloqueio.autor_email
        for bloqueio in ConteudoBloqueado.objects(criado_em__gte=desde).only("autor_email")
    )
    return [(email, total) for email, total in contagem.most_common() if total >= REINCIDENCIA_MIN]


@moderador_obrigatorio
def painel(request):
    estado = request.GET.get("estado", "pendentes")
    if estado not in dict(ESTADOS):
        estado = "pendentes"
    origem = request.GET.get("origem", "")
    if origem not in dict(ORIGENS):
        origem = ""

    consulta = ConteudoBloqueado.objects
    if estado == "pendentes":
        consulta = consulta.filter(revisado_em=None)
    elif estado == "revisados":
        consulta = consulta.filter(revisado_em__ne=None)
    if origem:
        consulta = consulta.filter(origem__startswith=f"{origem}:")

    pagina, parametros = paginar(request, consulta.order_by("-criado_em"), POR_PAGINA)
    # Uma lista de verdade: o template a percorre, e uma consulta percorrida
    # duas vezes devolveria objetos novos, sem o rótulo posto aqui.
    bloqueios = list(pagina.object_list)
    for bloqueio in bloqueios:
        bloqueio.rotulo_origem = rotulo_da_origem(bloqueio.origem)

    agora = datetime.datetime.utcnow()
    return render(
        request,
        "moderacao/painel.html",
        {
            "pagina": pagina,
            "bloqueios": bloqueios,
            "parametros": parametros,
            "estado": estado,
            "estados": ESTADOS,
            "origem": origem,
            "origens": ORIGENS,
            "total_pendentes": ConteudoBloqueado.objects(revisado_em=None).count(),
            "total_falsos_positivos": ConteudoBloqueado.objects(decisao="falso_positivo").count(),
            "total": ConteudoBloqueado.objects.count(),
            "reincidentes": _reincidentes(agora),
            "reincidencia_min": REINCIDENCIA_MIN,
            "reincidencia_dias": REINCIDENCIA_DIAS,
            "retencao_dias": RETENCAO_DIAS,
            "volta": request.get_full_path(),
        },
    )


@moderador_obrigatorio
@require_POST
def revisar(request, bloqueio_id):
    """Marca um registro como bloqueio correto, falso positivo, ou volta a deixá-lo
    pendente. Depois volta para a lista de onde a pessoa veio."""
    decisao = request.POST.get("decisao", "")
    if decisao not in DECISOES_ACEITAS:
        messages.error(request, "Escolha uma das opções de revisão.")
        return redirect("painel_moderacao")

    try:
        bloqueio = ConteudoBloqueado.objects(id=bloqueio_id).first()
    except MongoValidationError:
        bloqueio = None
    if bloqueio is None:
        raise Http404("Registro não encontrado.")

    if decisao == "pendente":
        bloqueio.revisado_em = None
        bloqueio.decisao = None
        bloqueio.revisado_por = None
    else:
        bloqueio.revisado_em = datetime.datetime.utcnow()
        bloqueio.decisao = decisao
        bloqueio.revisado_por = usuario_atual(request).username
    bloqueio.save()

    messages.success(request, "Revisão registrada.")
    volta = request.POST.get("volta", "")
    # Só volta para páginas deste painel (nunca para endereço de outro site).
    if volta.startswith("/moderacao/") and not volta.startswith("//"):
        return redirect(volta)
    return redirect("painel_moderacao")
