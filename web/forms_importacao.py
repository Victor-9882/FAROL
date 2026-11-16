"""Formulários das importações de frequência, simulados e redação (RF003 a RF005)."""

from datetime import date

from django import forms

from core.models import CicloCalendario
from ingestao.planilhas_casd import ABA_PRESENCA

from .forms_cadastro import _Data, validar_arquivo


class _ImportacaoForm(forms.Form):
    arquivo = forms.FileField(label="Planilha (.xlsx, .xlsm ou .csv)")
    ano = forms.IntegerField(label="Ano letivo", min_value=2000, max_value=2100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ano"].initial = date.today().year

    def clean_arquivo(self):
        return validar_arquivo(self.cleaned_data["arquivo"])


class ImportacaoFrequenciaForm(_ImportacaoForm):
    """Grade "Presença Anual" do CASD: o período é o das colunas de dia da planilha."""

    aba = forms.CharField(
        label="Aba da planilha",
        max_length=100,
        required=False,
        initial=ABA_PRESENCA,
        help_text="Nome da aba com a grade (por exemplo, Presença Anual ou Nivelamento).",
    )


class ImportacaoSimuladosForm(_ImportacaoForm):
    """Relatório de um simulado do P+: o arquivo não traz data, então o Diretor escolhe o ciclo
    (RN006)."""

    ciclo = forms.ModelChoiceField(
        label="Ciclo do simulado",
        queryset=CicloCalendario.objects.order_by("-data_inicio"),
        help_text="O ciclo do calendário em que este simulado conta.",
    )

    def clean(self):
        dados = super().clean()
        ciclo, ano = dados.get("ciclo"), dados.get("ano")
        if ciclo and ano and ciclo.data_inicio.year != ano:
            self.add_error("ciclo", "O ciclo precisa ser do ano letivo informado.")
        return dados


class ImportacaoRedacoesForm(_ImportacaoForm):
    """Exportação do Corrija-me de um tema: o arquivo não traz a data do tema, então o Diretor
    escolhe a terça-feira (RN007)."""

    terca = _Data(label="Terça-feira do tema", help_text="Dia em que o tema foi lançado (RN007).")

    def clean(self):
        dados = super().clean()
        terca, ano = dados.get("terca"), dados.get("ano")
        if terca:
            if terca.weekday() != 1:
                self.add_error("terca", "O tema é lançado numa terça-feira (RN007).")
            elif ano and terca.year != ano:
                self.add_error("terca", "A terça do tema precisa ser do ano letivo informado.")
        return dados
