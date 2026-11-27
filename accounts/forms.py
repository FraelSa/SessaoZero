"""
Formulários do accounts. Como Usuario é um Document do MongoEngine (não um
models.Model do Django), usamos django.forms.Form puro em vez de ModelForm,
e fazemos as validações de unicidade/senha manualmente nos métodos clean_*.
"""

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from campanhas.models import SISTEMAS_DA_LISTA
from core.horario import FUSOS_HORARIOS

from .avatares import AVATARES_PRONTOS
from .imagens import processar_foto
from .models import Usuario

# Opções da tela de preferências. Os sistemas vêm da mesma lista usada ao
# criar campanhas, assim o que o usuário marca aqui combina com o que existe.
SISTEMAS_PREFERENCIA = list(SISTEMAS_DA_LISTA)
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


# Regras de senha mostradas na tela. O mínimo de 8 caracteres, a recusa de
# senhas só com números e a de senhas comuns vêm de AUTH_PASSWORD_VALIDATORS
# (settings.py); o máximo é deste formulário.
SENHA_MAX_CARACTERES = 128
AJUDA_SENHA = (
    f"De 8 a {SENHA_MAX_CARACTERES} caracteres. "
    "Não pode ser só números nem uma senha muito comum."
)


def campo_senha_nova(rotulo):
    """Campo de senha nova com o indicador de força (partials/_forca_senha.html)."""
    campo = forms.CharField(
        label=rotulo,
        max_length=SENHA_MAX_CARACTERES,
        help_text=AJUDA_SENHA,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "data-senha-nova": ""}),
        error_messages={
            "max_length": f"A senha pode ter no máximo {SENHA_MAX_CARACTERES} caracteres."
        },
    )
    campo.indicador_senha = True
    return campo


def campo_confirmar_senha(rotulo):
    return forms.CharField(
        label=rotulo,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "data-senha-confirmar": ""}
        ),
    )


class CadastroForm(forms.Form):
    # RF01 - criação de conta
    username = forms.CharField(label="Nome de usuário", max_length=30, min_length=3)
    email = forms.EmailField(label="E-mail")
    senha = campo_senha_nova("Senha")
    confirmar_senha = campo_confirmar_senha("Confirmar senha")
    # RNF03 - o aceite da Política de Privacidade é obrigatório para criar a conta
    aceite_politica = forms.BooleanField(
        label="Li e concordo com a Política de Privacidade",
        error_messages={
            "required": "Para criar a conta, é preciso concordar com a Política de Privacidade."
        },
    )

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
    # RD04 - fuso horário da pessoa. Não entra em `preferencias` (que alimenta
    # a recomendação): é guardado em Usuario.fuso_horario.
    fuso_horario = forms.ChoiceField(
        label="Seu fuso horário",
        choices=FUSOS_HORARIOS,
        help_text=(
            "Horários de sessões, comentários, mensagens e avisos aparecem neste fuso. "
            "Ao marcar uma sessão, o horário que você digita também vale nele."
        ),
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
    nova_senha = campo_senha_nova("Nova senha")
    confirmar_nova_senha = campo_confirmar_senha("Confirmar nova senha")

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


BIO_MAX_CARACTERES = 500


class CampoTextoLongo(forms.CharField):
    """CharField para <textarea>: o navegador envia cada quebra de linha como
    dois caracteres (CR+LF) mas conta um só no `maxlength`; sem normalizar, um
    texto que cabia na tela seria recusado aqui por "passar do limite"."""

    def to_python(self, value):
        valor = super().to_python(value)
        return valor.replace("\r\n", "\n").replace("\r", "\n") if valor else valor


class PerfilForm(forms.Form):
    """Perfil: a biografia e a escolha do avatar (um desenho pronto, as iniciais
    do nome, a foto já enviada, ou uma foto nova, que tem prioridade sobre a
    escolha)."""

    # RF01 - biografia, mostrada no perfil público; passa pela moderação (RNF04).
    bio = CampoTextoLongo(
        label="Biografia",
        required=False,
        max_length=BIO_MAX_CARACTERES,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": BIO_MAX_CARACTERES}),
        help_text=(
            "Opcional. Conte como você joga e o que procura em uma mesa. Aparece no seu "
            f"perfil público e passa pela mesma moderação dos comentários (até {BIO_MAX_CARACTERES} caracteres)."
        ),
    )
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


class AlterarSenhaForm(forms.Form):
    # RF01 - editar a conta: trocar a senha estando logado
    senha_atual = forms.CharField(
        label="Senha atual",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    nova_senha = campo_senha_nova("Nova senha")
    confirmar_nova_senha = campo_confirmar_senha("Confirmar nova senha")

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_senha_atual(self):
        senha = self.cleaned_data["senha_atual"]
        if not self.usuario.checar_senha(senha):
            raise ValidationError("A senha atual não confere.")
        return senha

    def clean_nova_senha(self):
        senha = self.cleaned_data["nova_senha"]
        validate_password(senha)
        return senha

    def clean(self):
        dados = super().clean()
        nova = dados.get("nova_senha")
        confirmar = dados.get("confirmar_nova_senha")
        if nova and confirmar and nova != confirmar:
            self.add_error("confirmar_nova_senha", "As senhas não coincidem.")
        return dados


class AlterarUsernameForm(forms.Form):
    # RF01 - editar a conta: trocar o nome de usuário
    novo_username = forms.CharField(label="Novo nome de usuário", min_length=3, max_length=30)

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_novo_username(self):
        novo = self.cleaned_data["novo_username"].strip()
        if novo == self.usuario.username:
            raise ValidationError("Esse já é o seu nome de usuário.")
        # Mesma regra do cadastro: cadastros ainda não confirmados não seguram o nome.
        if Usuario.objects(
            username=novo, id__ne=self.usuario.id, aguardando_confirmacao__ne=True
        ).first():
            raise ValidationError("Esse nome de usuário já está em uso.")
        return novo


class AlterarEmailForm(forms.Form):
    # RF01 - editar a conta: trocar o e-mail. Pede a senha (o e-mail é o login e
    # o destino da recuperação de conta) e só vale depois de confirmado por link.
    novo_email = forms.EmailField(label="Novo e-mail")
    senha_atual = forms.CharField(
        label="Senha atual",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_novo_email(self):
        novo = self.cleaned_data["novo_email"].strip().lower()
        if novo == self.usuario.email:
            raise ValidationError("Esse já é o e-mail da sua conta.")
        if Usuario.objects(email=novo, id__ne=self.usuario.id, aguardando_confirmacao__ne=True).first():
            raise ValidationError("Já existe uma conta com esse e-mail.")
        return novo

    def clean_senha_atual(self):
        senha = self.cleaned_data["senha_atual"]
        if not self.usuario.checar_senha(senha):
            raise ValidationError("A senha atual não confere.")
        return senha


class ExcluirContaForm(forms.Form):
    # RF01 - excluir a conta, pedindo a senha e uma confirmação explícita
    senha = forms.CharField(label="Sua senha", widget=forms.PasswordInput)
    confirmacao = forms.BooleanField(
        label="Entendo que a exclusão é definitiva e não pode ser desfeita",
    )

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_senha(self):
        senha = self.cleaned_data["senha"]
        if not self.usuario.checar_senha(senha):
            raise ValidationError("Senha incorreta.")
        return senha
