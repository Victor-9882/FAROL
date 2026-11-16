"""Formulários do calendário letivo (RF007)."""

from datetime import date

from django import forms
from django.db import transaction

from core.auditoria import registrar_alteracoes
from core.calendario import aviso_duracao
from core.models import CicloCalendario, DiaCalendario, PeriodoLetivo, TemaRedacao
from ingestao.calendario import TIPOS

from .forms_cadastro import _Data, validar_arquivo


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


class _FormCalendario(forms.ModelForm):
    """Base dos formulários do calendário: todos os campos são editáveis e auditados (NF009).
    Os valores anteriores são capturados no `__init__`, antes de `is_valid()` alterar a
    instância."""

    def __init__(self, *args, autor, **kwargs):
        super().__init__(*args, **kwargs)
        self.autor = autor
        self._anteriores = {c: getattr(self.instance, c) for c in self._meta.fields}

    def save(self, commit=True):
        criando = self.instance._state.adding
        with transaction.atomic():
            objeto = super().save()
            if not criando:
                registrar_alteracoes(autor=self.autor, objeto=objeto, anteriores=self._anteriores)
        return objeto


class PeriodoForm(_FormCalendario):
    inicio = _Data(label="Início")
    fim = _Data(label="Fim")

    class Meta:
        model = PeriodoLetivo
        fields = ["inicio", "fim", "descricao"]


class DiaForm(_FormCalendario):
    data = _Data(label="Data")

    class Meta:
        model = DiaCalendario
        fields = ["data", "letivo", "descricao"]


class CicloForm(_FormCalendario):
    data_inicio = _Data(label="Início")
    data_fim = _Data(label="Fim")
    data_simulado = _Data(label="Data do simulado", required=False)

    class Meta:
        model = CicloCalendario
        fields = ["data_inicio", "data_fim", "data_simulado"]

    @property
    def aviso(self) -> str:
        return aviso_duracao(self.instance.data_inicio, self.instance.data_fim)


class TemaForm(_FormCalendario):
    data = _Data(label="Terça-feira")

    class Meta:
        model = TemaRedacao
        fields = ["data", "tema"]


FORMULARIOS = {"periodos": PeriodoForm, "dias": DiaForm, "ciclos": CicloForm, "temas": TemaForm}
