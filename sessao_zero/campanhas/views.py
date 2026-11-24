import datetime

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.auth_utils import login_obrigatorio, usuario_atual
from moderacao.filtros import moderar_texto
from moderacao.models import ConteudoBloqueado
from notificacoes.servicos import notificar, notificar_varios

from .forms import CampanhaForm, ComentarioForm
from .models import SISTEMAS_RPG_COMUNS, Campanha
from .recomendacoes import recomendar_campanhas
from .utils import buscar_campanha_ou_404


def listar_campanhas(request):
    """RF02 - listagem pública das campanhas abertas para novos jogadores."""
    campanhas = Campanha.objects.order_by("-criado_em")

    sistema_filtro = request.GET.get("sistema", "")
    if sistema_filtro:
        campanhas = campanhas.filter(sistema_rpg=sistema_filtro)

    return render(
        request,
        "campanhas/listar.html",
        {
            "campanhas": campanhas,
            "sistema_filtro": sistema_filtro,
            "sistemas": SISTEMAS_RPG_COMUNS,
        },
    )


def detalhe_campanha(request, campanha_id):
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)

    ja_inscrito = bool(usuario and usuario.email in campanha.jogadores_inscritos_emails)
    eh_mestre = bool(usuario and usuario.email == campanha.mestre_email)

    return render(
        request,
        "campanhas/detalhe.html",
        {
            "campanha": campanha,
            "comentario_form": ComentarioForm(),
            "ja_inscrito": ja_inscrito,
            "eh_mestre": eh_mestre,
        },
    )


@login_obrigatorio
def campanhas_recomendadas(request):
    """RF05 - campanhas recomendadas para o usuário logado, via TF-IDF."""
    usuario = usuario_atual(request)
    campanhas = recomendar_campanhas(usuario)

    tem_perfil = bool(
        (usuario.preferencias and any(usuario.preferencias.values()))
        or Campanha.objects(mestre_email=usuario.email).first()
        or Campanha.objects(jogadores_inscritos_emails=usuario.email).first()
    )

    return render(
        request,
        "campanhas/recomendadas.html",
        {"campanhas": campanhas, "tem_perfil": tem_perfil},
    )


@login_obrigatorio
def criar_campanha(request):
    """RF02 - criar campanha/sessão. Quem cria vira automaticamente o mestre."""
    usuario = usuario_atual(request)

    if request.method == "POST":
        form = CampanhaForm(request.POST)
        if form.is_valid():
            campanha = Campanha(
                titulo=form.cleaned_data["titulo"],
                sinopse=form.cleaned_data["sinopse"],
                sistema_rpg=form.cleaned_data["sistema_rpg"],
                max_jogadores=form.cleaned_data["max_jogadores"],
                data_sessao=form.cleaned_data["data_sessao"],
                mestre_email=usuario.email,
                mestre_username=usuario.username,
            )
            campanha.save()
            messages.success(request, "Campanha criada com sucesso!")
            return redirect("detalhe_campanha", campanha_id=campanha.id)
    else:
        form = CampanhaForm()

    return render(
        request,
        "campanhas/form.html",
        {"form": form, "titulo_pagina": "Nova campanha"},
    )


@login_obrigatorio
def editar_campanha(request, campanha_id):
    """RF02 - editar campanha. Só o mestre que a criou pode editar."""
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)

    if usuario.email != campanha.mestre_email:
        messages.error(request, "Só o mestre da campanha pode editá-la.")
        return redirect("detalhe_campanha", campanha_id=campanha.id)

    if request.method == "POST":
        form = CampanhaForm(request.POST)
        if form.is_valid():
            # RF07 - guardamos o estado anterior para comparar depois de
            # salvar e decidir o que notificar aos jogadores inscritos.
            data_sessao_antiga = campanha.data_sessao
            houve_mudanca_de_conteudo = (
                campanha.titulo != form.cleaned_data["titulo"]
                or campanha.sinopse != form.cleaned_data["sinopse"]
                or campanha.sistema_rpg != form.cleaned_data["sistema_rpg"]
                or campanha.max_jogadores != form.cleaned_data["max_jogadores"]
            )

            campanha.titulo = form.cleaned_data["titulo"]
            campanha.sinopse = form.cleaned_data["sinopse"]
            campanha.sistema_rpg = form.cleaned_data["sistema_rpg"]
            campanha.max_jogadores = form.cleaned_data["max_jogadores"]
            campanha.data_sessao = form.cleaned_data["data_sessao"]

            # Se abrirem mais vagas numa campanha que estava lotada, ela
            # volta a ficar "aberta" automaticamente.
            if campanha.status == "lotada" and campanha.vagas_livres > 0:
                campanha.status = "aberta"

            campanha.atualizado_em = datetime.datetime.utcnow()
            campanha.save()

            # RF07 - notifica todos os jogadores já inscritos sobre a
            # mudança de data e/ou de conteúdo da campanha.
            url_campanha = reverse("detalhe_campanha", args=[campanha.id])
            data_mudou = campanha.data_sessao != data_sessao_antiga

            if data_mudou and campanha.data_sessao:
                notificar_varios(
                    campanha.jogadores_inscritos_emails,
                    f'A campanha "{campanha.titulo}" tem nova data de sessão: '
                    f'{campanha.data_sessao.strftime("%d/%m/%Y %H:%M")}.',
                    url=url_campanha,
                )
            elif data_mudou and not campanha.data_sessao:
                notificar_varios(
                    campanha.jogadores_inscritos_emails,
                    f'A data da próxima sessão de "{campanha.titulo}" foi removida.',
                    url=url_campanha,
                )
            elif houve_mudanca_de_conteudo:
                notificar_varios(
                    campanha.jogadores_inscritos_emails,
                    f'A campanha "{campanha.titulo}" foi atualizada pelo mestre.',
                    url=url_campanha,
                )

            messages.success(request, "Campanha atualizada.")
            return redirect("detalhe_campanha", campanha_id=campanha.id)
    else:
        form = CampanhaForm(
            initial={
                "titulo": campanha.titulo,
                "sinopse": campanha.sinopse,
                "sistema_rpg": campanha.sistema_rpg,
                "max_jogadores": campanha.max_jogadores,
                "data_sessao": campanha.data_sessao,
            }
        )

    return render(
        request,
        "campanhas/form.html",
        {"form": form, "titulo_pagina": "Editar campanha", "campanha": campanha},
    )


@login_obrigatorio
def excluir_campanha(request, campanha_id):
    """RF02 - excluir campanha. Só o mestre pode excluir, com confirmação."""
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)

    if usuario.email != campanha.mestre_email:
        messages.error(request, "Só o mestre da campanha pode excluí-la.")
        return redirect("detalhe_campanha", campanha_id=campanha.id)

    if request.method == "POST":
        campanha.delete()
        messages.info(request, "Campanha excluída.")
        return redirect("listar_campanhas")

    return render(request, "campanhas/confirmar_exclusao.html", {"campanha": campanha})


@login_obrigatorio
def inscrever_campanha(request, campanha_id):
    """RF06 - inscrição de jogadores interessados, respeitando vagas livres."""
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)

    if request.method == "POST":
        if usuario.email == campanha.mestre_email:
            messages.error(request, "Você é o mestre desta campanha, não precisa se inscrever.")
        else:
            sucesso, mensagem = campanha.inscrever_jogador(usuario.email)
            messages.success(request, mensagem) if sucesso else messages.error(request, mensagem)

            if sucesso:
                # RF07 - avisa o mestre que uma vaga foi preenchida
                notificar(
                    campanha.mestre_email,
                    f'{usuario.username} se inscreveu na sua campanha "{campanha.titulo}".',
                    url=reverse("detalhe_campanha", args=[campanha.id]),
                )

    return redirect("detalhe_campanha", campanha_id=campanha.id)


@login_obrigatorio
def comentar_campanha(request, campanha_id):
    """RF08 - seção de comentários da campanha."""
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)

    if request.method == "POST":
        form = ComentarioForm(request.POST)
        if form.is_valid():
            texto = form.cleaned_data["texto"]

            # RNF04 - moderação em tempo real, antes de salvar o comentário.
            aceito, motivo = moderar_texto(texto)
            if not aceito:
                ConteudoBloqueado.objects.create(
                    autor_email=usuario.email,
                    texto_original=texto,
                    motivo=motivo,
                    origem=f"comentario:{campanha.id}",
                )
                messages.error(request, motivo)
                return redirect("detalhe_campanha", campanha_id=campanha.id)

            campanha.adicionar_comentario(usuario.email, usuario.username, texto)
            messages.success(request, "Comentário adicionado.")

            # RF07 - avisa o mestre quando alguém (que não é ele mesmo)
            # comenta na campanha.
            if usuario.email != campanha.mestre_email:
                notificar(
                    campanha.mestre_email,
                    f'{usuario.username} comentou na sua campanha "{campanha.titulo}".',
                    url=reverse("detalhe_campanha", args=[campanha.id]),
                )
        else:
            messages.error(request, "Não foi possível salvar o comentário.")

    return redirect("detalhe_campanha", campanha_id=campanha.id)
