"""Formulários das importações de frequência, simulados e redação (RF003 a RF005)."""

from datetime import date

from django import forms

from .forms_cadastro import _Data, validar_arquivo


class _ImportacaoForm(forms.Form):
    arquivo = forms.FileField(label="Planilha (.csv ou .xlsx)")
    ano = forms.IntegerField(label="Ano letivo", min_value=2000, max_value=2100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ano"].initial = date.today().year

    def clean_arquivo(self):
        return validar_arquivo(self.cleaned_data["arquivo"])


class ImportacaoFrequenciaForm(_ImportacaoForm):
    inicio = _Data(label="Início do período")
    fim = _Data(label="Fim do período")

    def clean(self):
        dados = super().clean()
        inicio, fim, ano = dados.get("inicio"), dados.get("fim"), dados.get("ano")
        if inicio and fim:
            if fim < inicio:
                self.add_error("fim", "O fim do período não pode ser anterior ao início.")
            elif ano and (inicio.year != ano or fim.year != ano):
                self.add_error("inicio", "O período precisa estar dentro do ano letivo informado.")
        return dados
