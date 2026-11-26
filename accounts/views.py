import datetime
import json
import logging
import math
import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.http import Http404, HttpResponse
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from mongoengine.errors import NotUniqueError

from campanhas.avaliacoes import avaliacoes_recebidas, reputacao
from campanhas.models import Campanha
from core import politica
from core.horario import FUSO_PADRAO, IDS_FUSOS

from .avatares import AVATARES_PRONTOS, IDS_AVATARES_PRONTOS, svg_iniciais
from .auth_utils import fazer_login, fazer_logout, login_obrigatorio, usuario_atual
from .exclusao import excluir_conta as executar_exclusao_de_conta
from .exportacao import montar_exportacao
from .exclusao import resumo_da_exclusao
from .forms import (
    ESTILOS_PREFERENCIA,
    SISTEMAS_PREFERENCIA,
    AlterarSenhaForm,
    CadastroForm,
    ExcluirContaForm,
    LoginForm,
    PerfilForm,
    PreferenciasForm,
    RedefinirSenhaForm,
    ReenviarConfirmacaoForm,
    SolicitarRecuperacaoForm,
)
from .models import CadastroPendente, FotoPerfil, Usuario

DURACAO_TOKEN_RECUPERACAO = datetime.timedelta(hours=1)
DURACAO_TOKEN_CONFIRMACAO = datetime.timedelta(hours=24)
INTERVALO_REENVIO = datetime.timedelta(seconds=60)

logger = logging.getLogger(__name__)


def _email_vai_para_o_terminal():
    """True quando o e-mail não é enviado de verdade (só impresso no terminal)."""
    return settings.EMAIL_BACKEND.endswith("console.EmailBackend")


def _enviar_email_confirmacao(request, pendente):
    """Manda o link de confirmação. Levanta exceção se o envio falhar (quem
    chama decide o que mostrar na tela)."""
    link = settings.SITE_URL.rstrip("/") + reverse("confirmar_email", args=[pendente.token])
    send_mail(
        subject="Sessão Zero - Confirme o seu e-mail",
        message=(
            f"Olá, {pendente.username}!\n\n"
            "Para criar a sua conta na Sessão Zero, confirme o seu e-mail "
            f"pelo link abaixo (válido por 24 horas):\n{link}\n\n"
            "Se você não pediu esse cadastro, pode ignorar este e-mail: "
            "nenhuma conta será criada."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[pendente.email],
    )


def _renovar_e_enviar(request, pendente):
    """Gera um link novo (com 24 horas de validade) e o envia. O link novo só
    é gravado depois que o e-mail saiu, então uma falha de envio não
    invalida o link anterior."""
    agora = datetime.datetime.utcnow()
    pendente.token = secrets.token_urlsafe(32)
    pendente.expira_em = agora + DURACAO_TOKEN_CONFIRMACAO
    _enviar_email_confirmacao(request, pendente)
    pendente.ultimo_envio_em = agora
    pendente.save()


def _segundos_ate_poder_reenviar(pendente):
    liberado_em = pendente.ultimo_envio_em + INTERVALO_REENVIO
    return max(math.ceil((liberado_em - datetime.datetime.utcnow()).total_seconds()), 0)


def cadastro(request):
    """RF01 - criar conta. A conta só é criada no banco depois que a pessoa
    confirma o e-mail (ver confirmar_email)."""
    if usuario_atual(request):
        return redirect("home")

    if request.method == "POST":
        form = CadastroForm(request.POST)
        if form.is_valid():
            pendente = CadastroPendente(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                senha_hash=make_password(form.cleaned_data["senha"]),
                token=secrets.token_urlsafe(32),
                expira_em=datetime.datetime.utcnow() + DURACAO_TOKEN_CONFIRMACAO,
                politica_aceita_em=datetime.datetime.utcnow(),  # RNF03
            )
            try:
                _enviar_email_confirmacao(request, pendente)
            except Exception:  # noqa: BLE001 - qualquer falha de SMTP
                logger.exception("Falha ao enviar e-mail de confirmação para %s", pendente.email)
                form.add_error(
                    None,
                    "Não conseguimos enviar o e-mail de confirmação agora. "
                    "Confira o endereço e tente de novo em instantes.",
                )
            else:
                # Um novo pedido para o mesmo e-mail substitui o anterior.
                CadastroPendente.objects(email=pendente.email).delete()
                pendente.save()
                request.session["email_pendente"] = pendente.email
                return redirect("verifique_email")
    else:
        form = CadastroForm()

    return render(request, "accounts/cadastro.html", {"form": form})


def verifique_email(request):
    """Tela de "confirme o seu e-mail", com a opção de pedir o link de novo."""
    email = request.session.get("email_pendente")
    pendente = CadastroPendente.objects(email=email).first() if email else None
    if pendente is None:
        return redirect("cadastro")

    if request.method == "POST":
        espera = _segundos_ate_poder_reenviar(pendente)
        if espera > 0:
            messages.error(request, f"Aguarde {espera} segundos para pedir um novo link.")
        else:
            try:
                _renovar_e_enviar(request, pendente)
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao reenviar e-mail de confirmação para %s", pendente.email)
                messages.error(request, "Não foi possível enviar o e-mail agora. Tente de novo em instantes.")
            else:
                messages.success(request, f"Enviamos um novo link para {pendente.email}.")
        return redirect("verifique_email")

    return render(
        request,
        "accounts/verifique_email.html",
        {"email": pendente.email, "email_no_terminal": _email_vai_para_o_terminal()},
    )


def login_view(request):
    """RF03 - validar login por e-mail e senha."""
    if usuario_atual(request):
        return redirect("home")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            senha = form.cleaned_data["senha"]
            usuario = Usuario.objects(email=email, ativo=True).first()

            # Mensagem de erro genérica de propósito: não dizemos se foi o
            # e-mail ou a senha que errou, para não facilitar tentativas de
            # descobrir quais e-mails têm conta cadastrada.
            if usuario is None or not usuario.checar_senha(senha):
                pendente = CadastroPendente.objects(email=email).first()
                if pendente is not None and check_password(senha, pendente.senha_hash):
                    # Quem acertou a senha de um cadastro ainda não confirmado
                    # precisa saber o que falta, em vez de ver "inválido".
                    form.add_error(
                        None,
                        "Falta confirmar o seu e-mail. Abra o link que enviamos no "
                        "cadastro, ou peça um novo abaixo.",
                    )
                else:
                    form.add_error(None, "E-mail ou senha inválidos.")
            elif usuario.aguardando_confirmacao:
                # Conta criada pela versão antiga, que gravava o usuário antes
                # da confirmação.
                form.add_error(
                    None,
                    "Confirme o seu e-mail antes de entrar. Procure o link que "
                    "enviamos no cadastro, ou peça um novo abaixo.",
                )
            else:
                fazer_login(request, usuario)
                messages.success(request, f"Login realizado. Bem-vindo(a) de volta, {usuario.username}!")
                return redirect("home")
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    fazer_logout(request)
    messages.info(request, "Você saiu da sua conta.")
    return redirect("home")


def confirmar_email(request, token):
    """Passo final do cadastro: o usuário clica no link recebido por e-mail e
    só então a conta é criada no banco."""
    agora = datetime.datetime.utcnow()
    pendente = CadastroPendente.objects(token=token, expira_em__gt=agora).first()

    if pendente is None:
        # Contas criadas pela versão antiga já estavam em "usuarios", só
        # marcadas como aguardando confirmação; o link delas continua valendo.
        legado = Usuario.objects(token_confirmacao=token, aguardando_confirmacao=True).first()
        if (
            legado is not None
            and legado.token_confirmacao_expira_em is not None
            and legado.token_confirmacao_expira_em > agora
        ):
            legado.aguardando_confirmacao = False
            legado.token_confirmacao = None
            legado.token_confirmacao_expira_em = None
            legado.save()
            messages.success(request, "E-mail confirmado! Agora você já pode entrar.")
            return redirect("login")

        messages.error(
            request,
            "Esse link de confirmação é inválido ou expirou. Peça um novo ou refaça o cadastro.",
        )
        return redirect("reenviar_confirmacao")

    # Outra pessoa pode ter criado uma conta com o mesmo e-mail ou nome de
    # usuário enquanto este cadastro esperava a confirmação.
    ja_existe = (
        Usuario.objects(email=pendente.email, aguardando_confirmacao__ne=True).first()
        or Usuario.objects(username=pendente.username, aguardando_confirmacao__ne=True).first()
    )
    if ja_existe is not None:
        pendente.delete()
        messages.error(
            request,
            "Esse e-mail ou nome de usuário já foi usado em outra conta. "
            "Se a conta for sua, entre normalmente; se não, refaça o cadastro.",
        )
        return redirect("login")

    # Remove restos de cadastros da versão antiga que nunca foram confirmados.
    Usuario.objects(aguardando_confirmacao=True, email=pendente.email).delete()
    Usuario.objects(aguardando_confirmacao=True, username=pendente.username).delete()

    usuario = Usuario(
        username=pendente.username,
        email=pendente.email,
        senha_hash=pendente.senha_hash,
        # RNF03 - cadastros pendentes antigos, de antes do aceite, ficam sem o registro.
        politica_aceita_em=pendente.politica_aceita_em,
        politica_versao=politica.VERSAO if pendente.politica_aceita_em else None,
    )
    try:
        usuario.save()
    except NotUniqueError:
        pendente.delete()
        messages.error(request, "Não foi possível criar a conta. Tente fazer o cadastro de novo.")
        return redirect("cadastro")

    pendente.delete()
    messages.success(request, "E-mail confirmado! Sua conta foi criada. Agora você já pode entrar.")
    return redirect("login")


def reenviar_confirmacao(request):
    """Pede um novo link de confirmação (o anterior expirou ou não chegou)."""
    if request.method == "POST":
        form = ReenviarConfirmacaoForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            pendente = CadastroPendente.objects(email=email).first()
            legado = None

            if pendente is None:
                # Conta da versão antiga, ainda em "usuarios": passa a ser um
                # cadastro pendente comum, e o registro antigo é apagado.
                legado = Usuario.objects(email=email, aguardando_confirmacao=True).first()
                if legado is not None:
                    pendente = CadastroPendente(
                        username=legado.username,
                        email=legado.email,
                        senha_hash=legado.senha_hash,
                        token=secrets.token_urlsafe(32),
                        expira_em=datetime.datetime.utcnow(),
                        ultimo_envio_em=datetime.datetime(1970, 1, 1),
                    )

            if pendente is not None and _segundos_ate_poder_reenviar(pendente) == 0:
                try:
                    _renovar_e_enviar(request, pendente)
                except Exception:  # noqa: BLE001
                    logger.exception("Falha ao reenviar e-mail de confirmação para %s", email)
                    messages.error(request, "Não foi possível enviar o e-mail agora. Tente de novo em instantes.")
                    return redirect("reenviar_confirmacao")
                if legado is not None:
                    legado.delete()

            # Mesma resposta exista ou não o cadastro, para não revelar quais
            # e-mails estão cadastrados.
            messages.success(
                request,
                "Se houver um cadastro aguardando confirmação para esse e-mail, "
                "enviamos um novo link.",
            )
            return redirect("login")
    else:
        form = ReenviarConfirmacaoForm()

    return render(request, "accounts/reenviar_confirmacao.html", {"form": form})


_CACHE_AVATAR = "public, max-age=30"


def avatar_usuario(request, username):
    """Entrega o avatar de um usuário como imagem: a foto enviada, o desenho
    pronto ou as iniciais. Ficar numa rota própria permite usar
    <img src="..."> em qualquer página sem buscar o usuário no template.
    Nome desconhecido (ou ?padrao=1) devolve as iniciais."""
    usuario = Usuario.objects(
        username=username, ativo=True, aguardando_confirmacao__ne=True
    ).first()

    if usuario is not None and not request.GET.get("padrao"):
        if usuario.tem_foto:
            foto = FotoPerfil.objects(usuario_id=str(usuario.id)).first()
            if foto is not None:
                resposta = HttpResponse(bytes(foto.dados), content_type="image/jpeg")
                resposta["Cache-Control"] = _CACHE_AVATAR
                return resposta
        if usuario.avatar_preset in IDS_AVATARES_PRONTOS:
            resposta = redirect(static(f"accounts/avatares/{usuario.avatar_preset}.svg"))
            resposta["Cache-Control"] = _CACHE_AVATAR
            return resposta

    resposta = HttpResponse(svg_iniciais(username), content_type="image/svg+xml")
    resposta["Cache-Control"] = _CACHE_AVATAR
    return resposta


def perfil_publico(request, username):
    """Página pública de uma pessoa: quem é, as avaliações que recebeu (RF06,
    como mestre e como jogador) e as campanhas que ela mestra. Só mostra o que
    já é público no resto do site; nunca o e-mail."""
    pessoa = Usuario.objects(
        username=username, ativo=True, aguardando_confirmacao__ne=True
    ).first()
    if pessoa is None:
        raise Http404("Pessoa não encontrada.")

    usuario = usuario_atual(request)
    return render(
        request,
        "accounts/perfil_publico.html",
        {
            "pessoa": pessoa,
            "eh_proprio": bool(usuario and usuario.id == pessoa.id),
            "como_mestre": reputacao(pessoa.email, "mestre"),
            "como_jogador": reputacao(pessoa.email, "jogador"),
            "avaliacoes": avaliacoes_recebidas(pessoa.email),
            "campanhas_mestradas": list(Campanha.objects(mestre_email=pessoa.email)[:10]),
        },
    )


@login_obrigatorio
def editar_perfil(request):
    """Perfil do usuário: por enquanto, a escolha do avatar."""
    usuario = usuario_atual(request)

    if request.method == "POST":
        form = PerfilForm(request.POST, request.FILES, tem_foto=usuario.tem_foto)
        if form.is_valid():
            escolha = form.cleaned_data["avatar"]
            foto = form.cleaned_data["foto"]  # bytes já tratados, ou None
            usuario_id = str(usuario.id)

            if foto:
                FotoPerfil.objects(usuario_id=usuario_id).update_one(
                    set__dados=foto,
                    set__atualizado_em=datetime.datetime.utcnow(),
                    upsert=True,
                )
                usuario.tem_foto = True
                usuario.avatar_preset = ""
            elif escolha == "foto":
                pass  # mantém a foto que já existe
            else:
                # Escolher um desenho (ou as iniciais) apaga a foto enviada.
                FotoPerfil.objects(usuario_id=usuario_id).delete()
                usuario.tem_foto = False
                usuario.avatar_preset = escolha if escolha in IDS_AVATARES_PRONTOS else ""

            usuario.avatar_versao = (usuario.avatar_versao or 0) + 1
            usuario.save()
            messages.success(request, "Perfil atualizado.")
            return redirect("editar_perfil")
    else:
        if usuario.tem_foto:
            atual = "foto"
        elif usuario.avatar_preset in IDS_AVATARES_PRONTOS:
            atual = usuario.avatar_preset
        else:
            atual = "iniciais"
        form = PerfilForm(initial={"avatar": atual}, tem_foto=usuario.tem_foto)

    url_avatar = reverse("avatar_usuario", args=[usuario.username])
    opcoes_avatar = [{"valor": "iniciais", "nome": "Iniciais", "src": url_avatar + "?padrao=1"}]
    opcoes_avatar += [
        {"valor": i, "nome": nome, "src": static(f"accounts/avatares/{i}.svg")}
        for i, nome in AVATARES_PRONTOS
    ]
    if usuario.tem_foto:
        opcoes_avatar.append(
            {"valor": "foto", "nome": "Minha foto", "src": f"{url_avatar}?v={usuario.avatar_versao}"}
        )

    # Marca a opção vigente também quando o formulário volta com erro.
    escolhido = request.POST.get("avatar") if request.method == "POST" else form.initial["avatar"]

    return render(
        request,
        "accounts/perfil.html",
        {"form": form, "opcoes_avatar": opcoes_avatar, "avatar_escolhido": escolhido, "usuario": usuario},
    )


@login_obrigatorio
def editar_preferencias(request):
    """RF05 - preferências que alimentam a recomendação de campanhas."""
    usuario = usuario_atual(request)
    preferencias_atuais = usuario.preferencias or {}

    if request.method == "POST":
        form = PreferenciasForm(request.POST)
        if form.is_valid():
            usuario.preferencias = form.para_preferencias()
            usuario.notificar_por_email = form.cleaned_data["receber_emails"]
            usuario.fuso_horario = form.cleaned_data["fuso_horario"]
            usuario.save()
            messages.success(request, "Preferências atualizadas.")
            return redirect("editar_preferencias")
    else:
        # Só marca o que ainda existe nas opções (valores antigos, digitados
        # à mão numa versão anterior da tela, são ignorados).
        form = PreferenciasForm(
            initial={
                "sistemas_favoritos": [
                    s for s in preferencias_atuais.get("sistemas_favoritos", [])
                    if s in SISTEMAS_PREFERENCIA
                ],
                "estilos_favoritos": [
                    e for e in preferencias_atuais.get("estilos_favoritos", [])
                    if e in ESTILOS_PREFERENCIA
                ],
                "receber_emails": usuario.notificar_por_email,
                "fuso_horario": (
                    usuario.fuso_horario if usuario.fuso_horario in IDS_FUSOS else FUSO_PADRAO
                ),
            }
        )

    return render(request, "accounts/preferencias.html", {"form": form})


@login_obrigatorio
def minha_conta(request):
    """RF01 - editar a conta: trocar a senha (com a senha atual). A exclusão da
    conta tem tela própria, com confirmação."""
    usuario = usuario_atual(request)

    if request.method == "POST":
        form = AlterarSenhaForm(request.POST, usuario=usuario)
        if form.is_valid():
            usuario.set_senha(form.cleaned_data["nova_senha"])
            # Qualquer link de recuperação pendente deixa de valer.
            usuario.token_recuperacao_senha = None
            usuario.token_recuperacao_expira_em = None
            usuario.save()
            messages.success(request, "Senha alterada.")
            return redirect("minha_conta")
    else:
        form = AlterarSenhaForm(usuario=usuario)

    return render(request, "accounts/minha_conta.html", {"form": form, "usuario": usuario})


@login_obrigatorio
def exportar_dados(request):
    """RNF03 - baixar uma cópia dos próprios dados em JSON (acesso e
    portabilidade). O download é um POST para não ser disparado por um link."""
    usuario = usuario_atual(request)

    if request.method == "POST":
        conteudo = json.dumps(montar_exportacao(usuario), ensure_ascii=False, indent=2)
        resposta = HttpResponse(conteudo, content_type="application/json; charset=utf-8")
        nome = f"sessao-zero-meus-dados-{datetime.date.today():%Y-%m-%d}.json"
        resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        resposta["Cache-Control"] = "no-store"
        return resposta

    return render(request, "accounts/exportar_dados.html")


@login_obrigatorio
def excluir_conta(request):
    """RF01 - excluir a própria conta. Pede a senha e uma confirmação; o que
    acontece com campanhas, comentários e mensagens está em accounts/exclusao.py."""
    usuario = usuario_atual(request)

    if request.method == "POST":
        form = ExcluirContaForm(request.POST, usuario=usuario)
        if form.is_valid():
            executar_exclusao_de_conta(usuario)
            fazer_logout(request)
            messages.info(request, "Sua conta foi excluída. Sentiremos sua falta na mesa!")
            return redirect("home")
    else:
        form = ExcluirContaForm(usuario=usuario)

    return render(
        request,
        "accounts/excluir_conta.html",
        {"form": form, "resumo": resumo_da_exclusao(usuario)},
    )


def solicitar_recuperacao_senha(request):
    """RF04 - passo 1: usuário informa o e-mail e recebe um link de redefinição."""
    if request.method == "POST":
        form = SolicitarRecuperacaoForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            usuario = Usuario.objects(email=email, ativo=True).first()

            if usuario:
                usuario.token_recuperacao_senha = secrets.token_urlsafe(32)
                usuario.token_recuperacao_expira_em = (
                    datetime.datetime.utcnow() + DURACAO_TOKEN_RECUPERACAO
                )
                usuario.save()

                link = settings.SITE_URL.rstrip("/") + reverse(
                    "redefinir_senha", args=[usuario.token_recuperacao_senha]
                )
                send_mail(
                    subject="Sessão Zero - Redefinição de senha",
                    message=(
                        f"Olá, {usuario.username}!\n\n"
                        f"Use o link abaixo para escolher uma nova senha "
                        f"(válido por 1 hora):\n{link}\n\n"
                        "Se você não pediu isso, pode ignorar este e-mail."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[usuario.email],
                )

            # Mensagem igual exista ou não a conta, para não revelar quais
            # e-mails estão cadastrados no sistema.
            messages.success(
                request,
                "Se houver uma conta com esse e-mail, enviamos um link de "
                "redefinição de senha para ela.",
            )
            return redirect("login")
    else:
        form = SolicitarRecuperacaoForm()

    return render(request, "accounts/solicitar_recuperacao_senha.html", {"form": form})


def redefinir_senha(request, token):
    """RF04 - passo 2: usuário define a nova senha a partir do link recebido."""
    usuario = Usuario.objects(token_recuperacao_senha=token).first()
    token_valido = (
        usuario is not None
        and usuario.token_recuperacao_expira_em is not None
        and usuario.token_recuperacao_expira_em > datetime.datetime.utcnow()
    )

    if not token_valido:
        messages.error(request, "Esse link de redefinição é inválido ou expirou.")
        return redirect("solicitar_recuperacao_senha")

    if request.method == "POST":
        form = RedefinirSenhaForm(request.POST)
        if form.is_valid():
            usuario.set_senha(form.cleaned_data["nova_senha"])
            usuario.token_recuperacao_senha = None
            usuario.token_recuperacao_expira_em = None
            usuario.save()
            messages.success(request, "Senha redefinida! Já pode fazer login.")
            return redirect("login")
    else:
        form = RedefinirSenhaForm()

    return render(request, "accounts/redefinir_senha.html", {"form": form})
