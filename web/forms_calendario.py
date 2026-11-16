"""Formulários do calendário letivo (RF007)."""

from datetime import date

from django import forms

from ingestao.calendario import TIPOS

from .forms_cadastro import validar_arquivo


class ImportacaoCalendarioForm(forms.Form):
    tipo = forms.ChoiceField(
        label="O que importar", choices=[(k, t.rotulo) for k, t in TIPOS.items()]
    )
    arquivo = forms.FileField(label="Planilha (.csv ou .xlsx)")
    ano = forms.IntegerField(label="Ano letivo", min_value=2000, max_value=2100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ano"].initial = date.today().year

    def clean_arquivo(self):
        return validar_arquivo(self.cleaned_data["arquivo"])
