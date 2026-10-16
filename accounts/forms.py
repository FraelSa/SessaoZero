"""
Formulários do accounts. Como Usuario é um Document do MongoEngine (não um
models.Model do Django), usamos django.forms.Form puro em vez de ModelForm,
e fazemos as validações de unicidade/senha manualmente nos métodos clean_*.
"""

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from campanhas.models import SISTEMAS_RPG_COMUNS

from .avatares import AVATARES_PRONTOS, IDS_AVATARES_PRONTOS
from .imagens import processar_foto
from .models import Usuario

# Opções da tela de preferências. Os sistemas vêm da mesma lista usada ao
# criar campanhas, assim o que o usuário marca aqui combina com o que existe.
SISTEMAS_PREFERENCIA = [s for s in SISTEMAS_RPG_COMUNS if s != "Outro"]
ESTILOS_PREFERENCIA = (
    "Terror",
    "Investigação",
    "Mistério",
    "Fantasia épica",
    "Aventura",
    "Ficção científica",
    "Cyberpunk",
    "Pós-apocalíptico",
    "Sobrenatural",
    "Drama e intriga política",
    "Exploração de masmorras",
    "Comédia",
)


class CadastroForm(forms.Form):
    # RF01 - criação de conta
    username = forms.CharField(label="Nome de usuário", max_length=30, min_length=3)
    email = forms.EmailField(label="E-mail")
    senha = forms.CharField(label="Senha", widget=forms.PasswordInput)
    confirmar_senha = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if Usuario.objects(username=username, aguardando_confirmacao__ne=True).first():
            raise ValidationError("Esse nome de usuário já está em uso.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Usuario.objects(email=email, aguardando_confirmacao__ne=True).first():
            raise ValidationError("Já existe uma conta com esse e-mail.")
        return email

    def clean_senha(self):
        senha = self.cleaned_data["senha"]
        # Usa os mesmos validadores de força de senha do Django
        # (AUTH_PASSWORD_VALIDATORS em settings.py) — cobre o RNF02.
        validate_password(senha)
        return senha

    def clean(self):
        cleaned_data = super().clean()
        senha = cleaned_data.get("senha")
        confirmar_senha = cleaned_data.get("confirmar_senha")
        if senha and confirmar_senha and senha != confirmar_senha:
            self.add_error("confirmar_senha", "As senhas não coincidem.")
        return cleaned_data


class LoginForm(forms.Form):
    # RF03 - validar login por e-mail e senha
    email = forms.EmailField(label="E-mail")
    senha = forms.CharField(label="Senha", widget=forms.PasswordInput)


class PreferenciasForm(forms.Form):
    # RF05 - preferências explícitas do usuário, usadas na recomendação
    # por TF-IDF (ver campanhas/recomendacoes.py).
    sistemas_favoritos = forms.MultipleChoiceField(
        label="Sistemas de RPG favoritos",
        required=False,
        choices=[(s, s) for s in SISTEMAS_PREFERENCIA],
        widget=forms.CheckboxSelectMultiple,
    )
    estilos_favoritos = forms.MultipleChoiceField(
        label="Estilos e temas que você curte",
        required=False,
        choices=[(e, e) for e in ESTILOS_PREFERENCIA],
        widget=forms.CheckboxSelectMultiple,
    )
    receber_emails = forms.BooleanField(
        label="Receber avisos por e-mail",
        required=False,
        help_text="Mudança de data, edições na campanha, novas inscrições e comentários.",
    )

    def para_preferencias(self):
        """Listas de strings, prontas para salvar em Usuario.preferencias."""
        return {
            "sistemas_favoritos": list(self.cleaned_data["sistemas_favoritos"]),
            "estilos_favoritos": list(self.cleaned_data["estilos_favoritos"]),
        }


class SolicitarRecuperacaoForm(forms.Form):
    # RF04 - recuperação de conta, primeiro passo: informar o e-mail
    email = forms.EmailField(label="E-mail cadastrado")


class RedefinirSenhaForm(forms.Form):
    # RF04 - segundo passo: escolher a nova senha
    nova_senha = forms.CharField(label="Nova senha", widget=forms.PasswordInput)
    confirmar_nova_senha = forms.CharField(
        label="Confirmar nova senha", widget=forms.PasswordInput
    )

    def clean_nova_senha(self):
        senha = self.cleaned_data["nova_senha"]
        validate_password(senha)
        return senha

    def clean(self):
        cleaned_data = super().clean()
        nova_senha = cleaned_data.get("nova_senha")
        confirmar = cleaned_data.get("confirmar_nova_senha")
        if nova_senha and confirmar and nova_senha != confirmar:
            self.add_error("confirmar_nova_senha", "As senhas não coincidem.")
        return cleaned_data


class ReenviarConfirmacaoForm(forms.Form):
    email = forms.EmailField(label="E-mail do cadastro")


class PerfilForm(forms.Form):
    """Escolha do avatar: um desenho pronto, as iniciais do nome, a foto já
    enviada, ou uma foto nova (que tem prioridade sobre a escolha)."""

    avatar = forms.ChoiceField(
        choices=[("iniciais", "Iniciais"), *AVATARES_PRONTOS, ("foto", "Minha foto")],
        widget=forms.RadioSelect,
    )
    foto = forms.FileField(
        label="Ou envie uma foto",
        required=False,
        help_text="JPG, PNG, WEBP ou GIF, até 2 MB. Ela é cortada em quadrado. "
                  "Se enviar uma foto, ela substitui o avatar escolhido acima.",
        widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp,image/gif"}),
    )

    def __init__(self, *args, tem_foto=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.tem_foto = tem_foto

    def clean_foto(self):
        arquivo = self.cleaned_data.get("foto")
        if not arquivo:
            return None
        try:
            return processar_foto(arquivo)
        except ValueError as erro:
            raise ValidationError(str(erro))

    def clean(self):
        dados = super().clean()
        if dados.get("avatar") == "foto" and not self.tem_foto and not dados.get("foto"):
            self.add_error("avatar", "Você ainda não enviou nenhuma foto.")
        return dados
