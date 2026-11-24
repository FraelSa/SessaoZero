from django import forms

from .models import SISTEMAS_RPG_COMUNS


class CampanhaForm(forms.Form):
    # RF02 - criar/editar campanhas e sessões
    titulo = forms.CharField(label="Título", max_length=120)
    sistema_rpg = forms.ChoiceField(
        label="Sistema de RPG",
        choices=[(sistema, sistema) for sistema in SISTEMAS_RPG_COMUNS],
    )
    sinopse = forms.CharField(
        label="Sinopse", max_length=3000, widget=forms.Textarea(attrs={"rows": 6})
    )
    max_jogadores = forms.IntegerField(label="Vagas de jogadores", min_value=1, max_value=50)
    # RF07 - data da próxima sessão, usada para notificar os jogadores
    # quando for definida ou alterada.
    data_sessao = forms.DateTimeField(
        label="Data da próxima sessão",
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )


class ComentarioForm(forms.Form):
    # RF08 - comentários na campanha
    texto = forms.CharField(
        label="",
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Escreva um comentário..."}),
    )
