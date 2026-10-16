import datetime
import secrets

from django.conf import settings
from django.http import HttpResponse
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from mongoengine.errors import NotUniqueError

from .avatares import AVATARES_PRONTOS, IDS_AVATARES_PRONTOS, svg_iniciais
from .auth_utils import fazer_login, fazer_logout, login_obrigatorio, usuario_atual
from .forms import (
    ESTILOS_PREFERENCIA,
    SISTEMAS_PREFERENCIA,
    CadastroForm,
    LoginForm,
    PerfilForm,
    PreferenciasForm,
    RedefinirSenhaForm,
    ReenviarConfirmacaoForm,
    SolicitarRecuperacaoForm,
)
from .models import FotoPerfil, Usuario

DURACAO_TOKEN_RECUPERACAO = datetime.timedelta(hours=1)
DURACAO_TOKEN_CONFIRMACAO = datetime.timedelta(hours=24)


def _enviar_email_confirmacao(request, usuario):
    """Gera um token novo e manda o link de confirmação para o e-mail do
    usuário. Levanta exceção se o envio falhar (quem chama decide o que
    mostrar na tela)."""
    usuario.token_confirmacao = secrets.token_urlsafe(32)
    usuario.token_confirmacao_expira_em = (
        datetime.datetime.utcnow() + DURACAO_TOKEN_CONFIRMACAO
    )
    usuario.save()

    link = request.build_absolute_uri(
        reverse("confirmar_email", args=[usuario.token_confirmacao])
    )
    send_mail(
        subject="Sessão Zero - Confirme o seu e-mail",
        message=(
            f"Olá, {usuario.username}!\n\n"
            "Para ativar a sua conta na Sessão Zero, confirme o seu e-mail "
            f"pelo link abaixo (válido por 24 horas):\n{link}\n\n"
            "Se você não criou essa conta, pode ignorar este e-mail."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[usuario.email],
    )


def cadastro(request):
    """RF01 - criar conta."""
    if usuario_atual(request):
        return redirect("home")

    if request.method == "POST":
        form = CadastroForm(request.POST)
        if form.is_valid():
            usuario = Usuario(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                aguardando_confirmacao=True,
            )
            usuario.set_senha(form.cleaned_data["senha"])

            # Cadastros antigos que nunca foram confirmados não podem
            # "prender" o e-mail ou o nome de usuário: quem se cadastra de
            # novo assume o lugar deles.
            Usuario.objects(aguardando_confirmacao=True, email=usuario.email).delete()
            Usuario.objects(aguardando_confirmacao=True, username=usuario.username).delete()

            try:
                usuario.save()
            except NotUniqueError:
                # As validações em CadastroForm já checam duplicidade, mas
                # não cobrem 100% o caso de dois cadastros simultâneos; o
                # índice único do Mongo garante a segurança final, e aqui
                # só evitamos que isso vire um erro 500 para o usuário.
                form.add_error(None, "Nome de usuário ou e-mail já em uso. Tente novamente.")
            else:
                try:
                    _enviar_email_confirmacao(request, usuario)
                except Exception:  # noqa: BLE001 - falha de SMTP não deve derrubar o cadastro
                    messages.error(
                        request,
                        "Sua conta foi criada, mas não conseguimos enviar o e-mail de "
                        "confirmação. Use a opção de reenviar abaixo.",
                    )
                    return redirect("reenviar_confirmacao")

                messages.success(
                    request,
                    f"Conta criada! Enviamos um link de confirmação para {usuario.email}. "
                    "Confirme o e-mail para poder entrar.",
                )
                return redirect("login")
    else:
        form = CadastroForm()

    return render(request, "accounts/cadastro.html", {"form": form})


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
                form.add_error(None, "E-mail ou senha inválidos.")
            elif usuario.aguardando_confirmacao:
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
    """Passo final do cadastro: o usuário clica no link recebido por e-mail."""
    usuario = Usuario.objects(token_confirmacao=token, aguardando_confirmacao=True).first()
    token_valido = (
        usuario is not None
        and usuario.token_confirmacao_expira_em is not None
        and usuario.token_confirmacao_expira_em > datetime.datetime.utcnow()
    )

    if not token_valido:
        messages.error(request, "Esse link de confirmação é inválido ou expirou. Peça um novo.")
        return redirect("reenviar_confirmacao")

    usuario.aguardando_confirmacao = False
    usuario.token_confirmacao = None
    usuario.token_confirmacao_expira_em = None
    usuario.save()

    messages.success(request, "E-mail confirmado! Agora você já pode entrar.")
    return redirect("login")


def reenviar_confirmacao(request):
    """Pede um novo link de confirmação (o anterior expirou ou não chegou)."""
    if request.method == "POST":
        form = ReenviarConfirmacaoForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            usuario = Usuario.objects(email=email, aguardando_confirmacao=True).first()
            if usuario:
                try:
                    _enviar_email_confirmacao(request, usuario)
                except Exception:  # noqa: BLE001
                    messages.error(request, "Não foi possível enviar o e-mail agora. Tente de novo em instantes.")
                    return redirect("reenviar_confirmacao")

            # Mesma resposta exista ou não a conta, para não revelar quais
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
            }
        )

    return render(request, "accounts/preferencias.html", {"form": form})


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

                link = request.build_absolute_uri(
                    reverse("redefinir_senha", args=[usuario.token_recuperacao_senha])
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
