"""Formulários do cadastro de alunos e turmas (RF006, NF009).

Atenção em `AlunoEdicaoForm`: só `nome` é campo do modelo. `data_ingresso`, `turma`,
`situacao`, `data_saida` e `data_mudanca` são declarados, porque `ModelForm.is_valid()`
altera a instância: se `turma` fosse campo do modelo, `mudar_turma()` veria a turma já
trocada e não gravaria o histórico (RN011). Aplicação e auditoria ficam no `save()`.
"""

import re
from datetime import date

from django import forms
from django.db import transaction

from core.auditoria import registrar_alteracoes
from core.models import Aluno, Turma
from ingestao import leitura

CAMPOS_AUDITADOS_ALUNO = ("nome", "data_ingresso", "turma", "situacao", "data_saida")


def _espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


class _Data(forms.DateField):
    widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")

    def __init__(self, **kwargs):
        super().__init__(input_formats=["%Y-%m-%d", "%d/%m/%Y"], **kwargs)


class AlunoNovoForm(forms.ModelForm):
    """Cria o aluno ativo; o `save()` do modelo abre o primeiro período de turma."""

    data_ingresso = _Data(label="Data de ingresso")

    class Meta:
        model = Aluno
        fields = ["matricula", "nome", "data_ingresso", "turma"]

    def clean_matricula(self):
        matricula = self.cleaned_data["matricula"].strip()
        if Aluno.objects.filter(pk=matricula).exists():
            raise forms.ValidationError("Já existe um aluno com esta matrícula.")
        return matricula

    def clean_nome(self):
        return _espacos(self.cleaned_data["nome"])


class AlunoEdicaoForm(forms.ModelForm):
    """Edita nome, ingresso, turma e situação; a matrícula é imutável (RN003)."""

    data_ingresso = _Data(label="Data de ingresso")
    turma = forms.ModelChoiceField(Turma.objects.all(), label="Turma atual")
    data_mudanca = _Data(
        label="Data da mudança de turma",
        required=False,
        help_text="Obrigatória ao trocar de turma; deve ser posterior ao início da turma atual.",
    )
    situacao = forms.ChoiceField(label="Situação", choices=Aluno.Situacao.choices)
    data_saida = _Data(label="Data de saída", required=False)

    class Meta:
        model = Aluno
        fields = ["nome"]

    def __init__(self, *args, autor, **kwargs):
        super().__init__(*args, **kwargs)
        self.autor = autor
        a = self.instance
        self._anteriores = {c: getattr(a, c) for c in CAMPOS_AUDITADOS_ALUNO}
        self.initial.update(
            data_ingresso=a.data_ingresso, turma=a.turma_id, situacao=a.situacao,
            data_saida=a.data_saida,
        )  # fmt: skip
        self._periodos = list(a.historico_turmas.order_by("data_inicio"))

    def clean(self):
        dados = super().clean()
        ingresso, turma = dados.get("data_ingresso"), dados.get("turma")
        if ingresso is None or turma is None:
            return dados
        primeiro = self._periodos[0] if self._periodos else None
        if primeiro and primeiro.data_fim and ingresso >= primeiro.data_fim:
            self.add_error(
                "data_ingresso", "O ingresso deve ser anterior à primeira mudança de turma."
            )
        if turma.pk != self.instance.turma_id:
            mudanca = dados.get("data_mudanca")
            atual = self._periodos[-1] if self._periodos else None
            inicio = ingresso if atual is primeiro else (atual.data_inicio if atual else ingresso)
            if mudanca is None:
                self.add_error("data_mudanca", "Informe a data da mudança de turma.")
            elif mudanca <= inicio:
                self.add_error(
                    "data_mudanca", "A mudança deve ser posterior ao início da turma atual."
                )
        situacao, saida = dados.get("situacao"), dados.get("data_saida")
        if situacao == Aluno.Situacao.ATIVO and saida:
            self.add_error("data_saida", "Aluno ativo não tem data de saída.")
        if situacao in (Aluno.Situacao.DESLIGADO, Aluno.Situacao.EVADIDO):
            if not saida:
                self.add_error("data_saida", "Informe a data de saída.")
            elif saida < ingresso:
                self.add_error("data_saida", "A saída não pode ser anterior ao ingresso.")
        return dados

    def clean_nome(self):
        return _espacos(self.cleaned_data["nome"])

    def save(self, commit=True):
        d = self.cleaned_data
        aluno = self.instance
        with transaction.atomic():
            if d["data_ingresso"] != self._anteriores["data_ingresso"]:
                aluno.corrigir_ingresso(d["data_ingresso"])
            aluno.situacao = d["situacao"]
            aluno.data_saida = d["data_saida"] if d["situacao"] != Aluno.Situacao.ATIVO else None
            aluno.save(update_fields=["nome", "situacao", "data_saida"])
            if d["turma"].pk != self._anteriores["turma"].pk:
                aluno.mudar_turma(d["turma"], d["data_mudanca"])
            registrar_alteracoes(autor=self.autor, objeto=aluno, anteriores=self._anteriores)
        return aluno


class TurmaForm(forms.ModelForm):
    class Meta:
        model = Turma
        fields = ["nome", "ano"]

    def __init__(self, *args, autor, **kwargs):
        super().__init__(*args, **kwargs)
        self.autor = autor
        self._anteriores = {"nome": self.instance.nome, "ano": self.instance.ano}

    def clean(self):
        dados = super().clean()
        if "nome" in dados:
            dados["nome"] = _espacos(dados["nome"])
        if dados.get("nome") and dados.get("ano"):
            repetida = Turma.objects.filter(nome__iexact=dados["nome"], ano=dados["ano"])
            if repetida.exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError("Já existe uma turma com este nome neste ano.")
        return dados

    def save(self, commit=True):
        criando = self.instance._state.adding
        with transaction.atomic():
            turma = super().save()
            if not criando:
                registrar_alteracoes(autor=self.autor, objeto=turma, anteriores=self._anteriores)
        return turma


class ImportacaoCadastroForm(forms.Form):
    arquivo = forms.FileField(label="Planilha (.csv ou .xlsx)")
    ano = forms.IntegerField(label="Ano letivo", min_value=2000, max_value=2100)
    data_mudanca = _Data(
        label="Data de mudança de turma",
        help_text="Usada quando o arquivo traz turma diferente da atual de um aluno existente.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = date.today()
        self.fields["ano"].initial = hoje.year
        self.fields["data_mudanca"].initial = hoje

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(leitura.EXTENSOES):
            raise forms.ValidationError("Envie um arquivo .csv ou .xlsx.")
        if arquivo.size > leitura.TAMANHO_MAXIMO:
            raise forms.ValidationError("O arquivo excede o tamanho máximo permitido.")
        return arquivo
