"""Formulário do relatório de auxílios (RF021, SM #80)."""

from datetime import date

from django import forms

from ingestao import leitura

LIMITE_BYTES = 1024 * 1024  # uma lista de matrículas é pequena; fica só em memória
ERRO_TAMANHO = "O arquivo é grande demais para uma lista de matrículas."


class RelatorioAuxiliosForm(forms.Form):
    arquivo = forms.FileField(
        label="Planilha de matrículas (.xlsx, .xlsm ou .csv)",
        help_text="Só a coluna matrícula. O arquivo não é guardado.",
    )
    ano = forms.IntegerField(label="Ano letivo", min_value=2000, max_value=2100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ano"].initial = date.today().year

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(leitura.EXTENSOES):
            raise forms.ValidationError("Envie um arquivo .csv, .xlsx ou .xlsm.")
        if arquivo.size > LIMITE_BYTES:
            raise forms.ValidationError(ERRO_TAMANHO)
        return arquivo
