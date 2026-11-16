"""Filtros do histórico de intervenções (RF020). Consulta somente leitura, só do Diretor."""

from django import forms
from django.db.models import Q

from core.models import Intervencao

PENDENTE = "PENDENTE"


class FiltroIntervencoesForm(forms.Form):
    aluno = forms.CharField(label="Aluno (matrícula ou nome)", required=False, max_length=150)
    tipo = forms.ChoiceField(
        label="Tipo", required=False, choices=[("", "Todos"), *Intervencao.Tipo.choices]
    )
    desfecho = forms.ChoiceField(
        label="Desfecho",
        required=False,
        choices=[
            ("", "Todos"),
            *Intervencao.Desfecho.choices,
            (PENDENTE, "Pendente (sem desfecho)"),
        ],
    )
    de = forms.DateField(label="De", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    ate = forms.DateField(
        label="Até", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    def clean(self):
        dados = super().clean()
        de, ate = dados.get("de"), dados.get("ate")
        if de and ate and de > ate:
            self.add_error("ate", "A data final não pode ser anterior à inicial.")
        return dados

    def aplicar(self, qs):
        """Filtra as intervenções. Busca de consulta, não associa nada a aluno (RN003)."""
        d = self.cleaned_data
        termo = (d.get("aluno") or "").strip()
        if termo:
            qs = qs.filter(Q(aluno__pk=termo) | Q(aluno__nome__icontains=termo))
        if d.get("tipo"):
            qs = qs.filter(tipo=d["tipo"])
        if d.get("desfecho") == PENDENTE:
            qs = qs.filter(desfecho="")
        elif d.get("desfecho"):
            qs = qs.filter(desfecho=d["desfecho"])
        if d.get("de"):
            qs = qs.filter(data__gte=d["de"])
        if d.get("ate"):
            qs = qs.filter(data__lte=d["ate"])
        return qs
