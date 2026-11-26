import datetime

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.auth_utils import login_obrigatorio, usuario_atual
from chat.models import MensagemChat
from core.horario import (
    descrever_sessao,
    para_horario_local,
    para_utc_com_fuso,
    para_utc_ingenuo,
    rotulo_fuso,
)
from moderacao.filtros import moderar_texto
from moderacao.models import ConteudoBloqueado
from notificacoes.servicos import notificar, notificar_varios

from .avaliacoes import (
    MOTIVO_AINDA_FECHADA,
    alvos_do_usuario,
    avaliacoes_abertas,
    reputacao,
    salvar_avaliacao,
)
from .busca import MAX_CARACTERES, filtrar_por_palavras
from .forms import AvaliacaoForm, CampanhaForm, ComentarioForm
from .models import SISTEMA_PROPRIO, SISTEMAS_DA_LISTA, SISTEMAS_RPG_COMUNS, Campanha
from .recomendacoes import recomendar_campanhas
from .utils import buscar_campanha_ou_404


def _rotulo_fuso_atual():
    """Nome amigável do fuso ativo na requisição (o da pessoa logada)."""
    return rotulo_fuso(timezone.get_current_timezone_name())


def _texto_da_data(data_utc):
    """'29/10/2026 21:00 (Salvador, Bahia)': o horário e o fuso em que o mestre
    o marcou, para aparecer certo nas notificações, que são texto fixo."""
    return f"{para_horario_local(data_utc):%d/%m/%Y %H:%M} ({_rotulo_fuso_atual()})"


def listar_campanhas(request):
    """RF02 - listagem pública das campanhas (todas, inclusive as lotadas),
    com filtro por sistema e busca por palavra-chave que se combinam."""
    campanhas = Campanha.objects.order_by("-criado_em")

    sistema_filtro = request.GET.get("sistema", "")
    if sistema_filtro == SISTEMA_PROPRIO:
        # Sistemas próprios ficam gravados com o nome que o mestre digitou.
        campanhas = campanhas.filter(sistema_rpg__nin=SISTEMAS_DA_LISTA)
    elif sistema_filtro:
        campanhas = campanhas.filter(sistema_rpg=sistema_filtro)

    busca = request.GET.get("q", "").strip()[:MAX_CARACTERES]
    if busca:
        campanhas = filtrar_por_palavras(campanhas, busca)

    return render(
        request,
        "campanhas/listar.html",
        {
            "campanhas": campanhas,
            "sistema_filtro": sistema_filtro,
            "sistemas": SISTEMAS_RPG_COMUNS,
            "busca": busca,
            "total": campanhas.count() if (busca or sistema_filtro) else None,
        },
    )


@login_obrigatorio
def minhas_campanhas(request):
    """RF02 - as campanhas que a pessoa logada criou (das quais é a mestre):
    primeiro as abertas e lotadas, depois as encerradas, das mais novas para
    as mais antigas."""
    usuario = usuario_atual(request)
    campanhas = list(Campanha.objects(mestre_email=usuario.email).order_by("-criado_em"))
    return render(
        request,
        "campanhas/minhas_campanhas.html",
        {
            "ativas": [c for c in campanhas if c.status != "encerrada"],
            "encerradas": [c for c in campanhas if c.status == "encerrada"],
            "total": len(campanhas),
        },
    )


@login_obrigatorio
def minhas_inscricoes(request):
    """RF07 - as campanhas em que a pessoa logada está inscrita como jogadora,
    em três grupos: com sessão marcada (a mais próxima primeiro), sem data
    definida e sessões únicas que já aconteceram."""
    usuario = usuario_atual(request)
    agora = datetime.datetime.utcnow()

    proximas, sem_data, realizadas = [], [], []
    for campanha in Campanha.objects(jogadores_inscritos_emails=usuario.email):
        proxima = campanha.proxima_sessao
        if proxima is None:
            sem_data.append(campanha)
        elif proxima <= agora:
            realizadas.append((proxima, campanha))
        else:
            proximas.append((proxima, campanha))

    proximas.sort(key=lambda par: par[0])
    realizadas.sort(key=lambda par: par[0], reverse=True)
    sem_data.sort(key=lambda campanha: campanha.criado_em, reverse=True)

    return render(
        request,
        "campanhas/minhas_inscricoes.html",
        {
            "proximas": [campanha for _, campanha in proximas],
            "sem_data": sem_data,
            "realizadas": [campanha for _, campanha in realizadas],
            "total": len(proximas) + len(sem_data) + len(realizadas),
        },
    )


def detalhe_campanha(request, campanha_id):
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)

    ja_inscrito = bool(usuario and usuario.email in campanha.jogadores_inscritos_emails)
    eh_mestre = bool(usuario and usuario.email == campanha.mestre_email)

    # RF06 - quem participa da campanha vê o formulário para avaliar os outros.
    alvos = alvos_do_usuario(campanha, usuario) if usuario else []

    return render(
        request,
        "campanhas/detalhe.html",
        {
            "campanha": campanha,
            "comentario_form": ComentarioForm(),
            "ja_inscrito": ja_inscrito,
            "eh_mestre": eh_mestre,
            "sessao": descrever_sessao(campanha),
            "reputacao_mestre": reputacao(campanha.mestre_email, "mestre"),
            "avaliacao_form": AvaliacaoForm(),
            "avaliacao_alvos": alvos,
            "avaliacoes_abertas": avaliacoes_abertas(campanha),
            "avaliacoes_fechadas_motivo": MOTIVO_AINDA_FECHADA,
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
        form = CampanhaForm(request.POST, rotulo_fuso=_rotulo_fuso_atual())
        if form.is_valid():
            dados = form.cleaned_data
            campanha = Campanha(
                titulo=dados["titulo"],
                sinopse=dados["sinopse"],
                sistema_rpg=form.sistema_escolhido,
                classificacao=dados["classificacao"],  # RD03
                temas_sensiveis=list(dados["temas_sensiveis"]),
                max_jogadores=dados["max_jogadores"],
                recorrencia=dados["recorrencia"],  # RD04
                # O horário digitado vale no fuso do mestre; grava em UTC.
                data_sessao=para_utc_ingenuo(dados["data_sessao"]),
                fuso_mestre=timezone.get_current_timezone_name(),
                mestre_email=usuario.email,
                mestre_username=usuario.username,
            )
            campanha.save()
            messages.success(request, "Campanha criada com sucesso!")
            return redirect("detalhe_campanha", campanha_id=campanha.id)
    else:
        form = CampanhaForm(rotulo_fuso=_rotulo_fuso_atual())

    return render(
        request,
        "campanhas/form.html",
        {"form": form, "titulo_pagina": "Nova campanha"},
    )


def _sistema_no_formulario(campanha):
    """Valores iniciais dos campos de sistema ao editar: um sistema da lista
    vem selecionado; qualquer outro nome vem como "Sistema Próprio", com o
    nome no campo de texto (o antigo "Outro" vem com o campo vazio)."""
    if campanha.sistema_rpg in SISTEMAS_DA_LISTA:
        return {"sistema_rpg": campanha.sistema_rpg, "sistema_proprio": ""}
    nome = "" if campanha.sistema_rpg in ("Outro", SISTEMA_PROPRIO) else campanha.sistema_rpg
    return {"sistema_rpg": SISTEMA_PROPRIO, "sistema_proprio": nome}


@login_obrigatorio
def editar_campanha(request, campanha_id):
    """RF02 - editar campanha. Só o mestre que a criou pode editar."""
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)

    if usuario.email != campanha.mestre_email:
        messages.error(request, "Só o mestre da campanha pode editá-la.")
        return redirect("detalhe_campanha", campanha_id=campanha.id)

    inscritos = len(campanha.jogadores_inscritos_emails)

    if request.method == "POST":
        form = CampanhaForm(
            request.POST, inscritos=inscritos, rotulo_fuso=_rotulo_fuso_atual()
        )
        if form.is_valid():
            dados = form.cleaned_data
            nova_data = para_utc_ingenuo(dados["data_sessao"])
            temas = list(dados["temas_sensiveis"])

            # RF08 - guardamos o estado anterior para comparar depois de
            # salvar e decidir o que notificar aos jogadores inscritos.
            data_sessao_antiga = campanha.data_sessao
            houve_mudanca_de_conteudo = (
                campanha.titulo != dados["titulo"]
                or campanha.sinopse != dados["sinopse"]
                or campanha.sistema_rpg != form.sistema_escolhido
                or campanha.max_jogadores != dados["max_jogadores"]
                or campanha.classificacao != dados["classificacao"]
                or sorted(campanha.temas_sensiveis or []) != sorted(temas)
                or campanha.recorrencia != dados["recorrencia"]
            )
            data_mudou = nova_data != data_sessao_antiga

            campanha.titulo = dados["titulo"]
            campanha.sinopse = dados["sinopse"]
            campanha.sistema_rpg = form.sistema_escolhido
            campanha.classificacao = dados["classificacao"]
            campanha.temas_sensiveis = temas
            campanha.max_jogadores = dados["max_jogadores"]
            campanha.recorrencia = dados["recorrencia"]
            campanha.data_sessao = nova_data
            if data_mudou:
                # O horário novo foi digitado no fuso de quem está editando.
                campanha.fuso_mestre = timezone.get_current_timezone_name()

            # Mantém o status coerente com as vagas: abrir mais vagas reabre
            # uma campanha lotada, e fechar até o número de inscritos a lota.
            campanha.sincronizar_status()

            campanha.atualizado_em = datetime.datetime.utcnow()
            campanha.save()

            # RF08 - notifica todos os jogadores já inscritos sobre a
            # mudança de data e/ou de conteúdo da campanha.
            url_campanha = reverse("detalhe_campanha", args=[campanha.id])

            if data_mudou and campanha.data_sessao:
                notificar_varios(
                    campanha.jogadores_inscritos_emails,
                    f'A campanha "{campanha.titulo}" tem nova data de sessão: '
                    f"{_texto_da_data(campanha.data_sessao)}.",
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
                **_sistema_no_formulario(campanha),
                # Campanhas antigas não têm classificação: o campo vem vazio e
                # o mestre precisa escolher uma ao salvar.
                "classificacao": campanha.classificacao or "",
                "temas_sensiveis": campanha.temas_sensiveis,
                "max_jogadores": campanha.max_jogadores,
                "recorrencia": campanha.recorrencia,
                # Com fuso (UTC): o formulário a mostra no fuso de quem edita.
                "data_sessao": para_utc_com_fuso(campanha.data_sessao),
            },
            inscritos=inscritos,
            rotulo_fuso=_rotulo_fuso_atual(),
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
        # As mensagens do chat pertencem à campanha: saem junto com ela.
        MensagemChat.objects(campanha_id=str(campanha.id)).delete()
        campanha.delete()
        messages.info(request, "Campanha excluída.")
        return redirect("listar_campanhas")

    return render(request, "campanhas/confirmar_exclusao.html", {"campanha": campanha})


@login_obrigatorio
def inscrever_campanha(request, campanha_id):
    """RF07 - inscrição de jogadores interessados, respeitando vagas livres."""
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)

    if request.method == "POST":
        if usuario.email == campanha.mestre_email:
            messages.error(request, "Você é o mestre desta campanha, não precisa se inscrever.")
        else:
            sucesso, mensagem = campanha.inscrever_jogador(usuario.email)
            messages.success(request, mensagem) if sucesso else messages.error(request, mensagem)

            if sucesso:
                # RF08 - avisa o mestre que uma vaga foi preenchida
                notificar(
                    campanha.mestre_email,
                    f'{usuario.username} se inscreveu na sua campanha "{campanha.titulo}".',
                    url=reverse("detalhe_campanha", args=[campanha.id]),
                )

    return redirect("detalhe_campanha", campanha_id=campanha.id)


@login_obrigatorio
def comentar_campanha(request, campanha_id):
    """RF09 - seção de comentários da campanha."""
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

            # RF08 - avisa o mestre quando alguém (que não é ele mesmo)
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


@login_obrigatorio
def avaliar_participante(request, campanha_id, username):
    """RF06 - o participante dá (ou atualiza) a nota de outro participante."""
    campanha = buscar_campanha_ou_404(campanha_id)
    usuario = usuario_atual(request)
    destino = redirect(reverse("detalhe_campanha", args=[campanha.id]) + "#avaliacoes")

    if request.method != "POST":
        return destino

    form = AvaliacaoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Escolha uma nota de 1 a 5. O comentário pode ter até 500 caracteres.")
        return destino

    comentario = form.cleaned_data["comentario"]

    # RNF04 - o comentário da avaliação passa pela mesma moderação dos demais.
    if comentario:
        aceito, motivo = moderar_texto(comentario)
        if not aceito:
            ConteudoBloqueado.objects.create(
                autor_email=usuario.email,
                texto_original=comentario,
                motivo=motivo,
                origem=f"avaliacao:{campanha.id}",
            )
            messages.error(request, motivo)
            return destino

    try:
        avaliacao, criada = salvar_avaliacao(
            campanha, usuario, username, form.cleaned_data["nota"], comentario
        )
    except ValueError as erro:
        messages.error(request, str(erro))
        return destino

    messages.success(
        request, "Avaliação enviada." if criada else "Avaliação atualizada."
    )

    # RF08 - avisa a pessoa avaliada, só na primeira vez (atualizar não repete).
    if criada:
        notificar(
            avaliacao.avaliado_email,
            f'{usuario.username} avaliou você na campanha "{campanha.titulo}".',
            url=reverse("perfil_publico", args=[avaliacao.avaliado_username]),
        )

    return destino
