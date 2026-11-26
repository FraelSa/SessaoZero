from django import forms

from core.horario import RECORRENCIAS

from .models import (
    CLASSIFICACOES_INDICATIVAS,
    SISTEMA_NOME_MAX,
    SISTEMA_PROPRIO,
    SISTEMAS_RPG_COMUNS,
    TEMAS_SENSIVEIS,
)


class CampanhaForm(forms.Form):
    # RF02 - criar/editar campanhas e sessões
    titulo = forms.CharField(label="Título", max_length=120)
    # RD01 - a mesa pode usar um sistema da lista ou um sistema próprio. Ao
    # escolher "Sistema Próprio", o campo abaixo aparece (campanha_form.js)
    # para digitar o nome.
    sistema_rpg = forms.ChoiceField(
        label="Sistema de RPG",
        choices=[(sistema, sistema) for sistema in SISTEMAS_RPG_COMUNS],
        widget=forms.Select(attrs={"data-sistema-proprio": SISTEMA_PROPRIO}),
    )
    sistema_proprio = forms.CharField(
        label="Nome do sistema",
        required=False,
        max_length=SISTEMA_NOME_MAX,
        help_text="Só para “Sistema Próprio”: escreva o nome do sistema que a mesa vai usar.",
    )
    sinopse = forms.CharField(
        label="Sinopse", max_length=3000, widget=forms.Textarea(attrs={"rows": 6})
    )
    # RD03 - classificação indicativa de conteúdo, definida pelo mestre
    classificacao = forms.ChoiceField(
        label="Classificação indicativa",
        choices=[("", "Escolha uma faixa")] + list(CLASSIFICACOES_INDICATIVAS),
        help_text="Faixa etária recomendada para esta mesa.",
    )
    temas_sensiveis = forms.MultipleChoiceField(
        label="Temas sensíveis que a mesa pode abordar",
        required=False,
        choices=TEMAS_SENSIVEIS,
        widget=forms.CheckboxSelectMultiple,
        help_text="Opcional. Aparecem na campanha para os jogadores saberem antes de entrar.",
    )
    max_jogadores = forms.IntegerField(label="Vagas de jogadores", min_value=1, max_value=50)
    # RD04 - recorrência e horário das sessões. O horário é digitado no fuso
    # de quem preenche (o fuso ativo na requisição) e gravado em UTC; quem
    # vê a campanha recebe o horário convertido para o próprio fuso.
    recorrencia = forms.ChoiceField(
        label="Frequência das sessões",
        choices=RECORRENCIAS,
        initial="unica",
    )
    # RF08 - data da próxima sessão, usada para notificar os jogadores
    # quando for definida ou alterada.
    data_sessao = forms.DateTimeField(
        label="Data e horário da sessão",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    def __init__(self, *args, inscritos=0, rotulo_fuso="", **kwargs):
        super().__init__(*args, **kwargs)
        self.inscritos = inscritos
        ajuda = "Horário no seu fuso"
        if rotulo_fuso:
            ajuda += f" ({rotulo_fuso}; dá para mudar em Preferências)"
        ajuda += ". Quem está em outro fuso vê o horário convertido."
        ajuda += " Nas sessões que se repetem, informe a data de uma delas: o site calcula a próxima."
        self.fields["data_sessao"].help_text = ajuda

    def clean_max_jogadores(self):
        vagas = self.cleaned_data["max_jogadores"]
        if vagas < self.inscritos:
            raise forms.ValidationError(
                f"A campanha já tem {self.inscritos} jogador(es) inscrito(s): "
                f"o mínimo de vagas é {self.inscritos}."
            )
        return vagas

    @property
    def sistema_escolhido(self):
        """O que é gravado em Campanha.sistema_rpg: o sistema da lista ou o
        nome digitado para o sistema próprio."""
        dados = self.cleaned_data
        if dados["sistema_rpg"] == SISTEMA_PROPRIO:
            return dados["sistema_proprio"]
        return dados["sistema_rpg"]

    def clean(self):
        dados = super().clean()
        if dados.get("sistema_rpg") == SISTEMA_PROPRIO:
            nome = (dados.get("sistema_proprio") or "").strip()
            dados["sistema_proprio"] = nome
            if not nome and "sistema_proprio" not in self.errors:
                self.add_error("sistema_proprio", "Escreva o nome do sistema próprio.")
        if (
            dados.get("recorrencia", "unica") != "unica"
            and not dados.get("data_sessao")
            and "data_sessao" not in self.errors
        ):
            self.add_error(
                "data_sessao",
                "Informe a data e o horário de uma sessão para calcular a recorrência.",
            )
        return dados


class ComentarioForm(forms.Form):
    # RF09 - comentários na campanha
    texto = forms.CharField(
        label="",
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Escreva um comentário..."}),
    )


class AvaliacaoForm(forms.Form):
    # RF06 - nota de 1 a 5 e comentário opcional sobre outro participante
    nota = forms.TypedChoiceField(
        label="Nota",
        choices=[
            (5, "5, excelente"),
            (4, "4, muito bom"),
            (3, "3, bom"),
            (2, "2, regular"),
            (1, "1, ruim"),
        ],
        coerce=int,
        error_messages={"invalid_choice": "Escolha uma nota de 1 a 5."},
    )
    comentario = forms.CharField(
        label="Comentário (opcional)",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2, "maxlength": 500}),
    )

    def clean_comentario(self):
        return self.cleaned_data["comentario"].strip()
