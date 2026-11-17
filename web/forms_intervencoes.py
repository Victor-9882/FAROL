"""Formulários de intervenções: filtros do histórico (RF020) e registro (RF019). Só do Diretor."""

from django import forms
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.auditoria import registrar_alteracoes
from core.models import Alerta, Intervencao

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


class IntervencaoForm(forms.ModelForm):
    """Registra uma intervenção sobre um aluno (RF019). `aluno` e `usuario` nunca vêm do POST."""

    class Meta:
        model = Intervencao
        fields = ["tipo", "data", "responsavel", "descricao", "alerta", "desfecho"]
        widgets = {"data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        labels = {"alerta": "Alerta de origem (opcional)"}

    def __init__(self, *args, aluno, autor, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.aluno = aluno
        self.instance.usuario = autor
        self.fields["alerta"].required = False
        self.fields["alerta"].queryset = (
            Alerta.objects.filter(aluno=aluno)
            .select_related("ciclo")
            .order_by("-ativo", "-data_geracao")
        )
        self.fields["alerta"].label_from_instance = self._rotulo_alerta
        self.fields["desfecho"].required = False

    @staticmethod
    def _rotulo_alerta(alerta):
        if alerta.semana:
            quando = f"semana de {alerta.semana:%d/%m/%Y}"
        elif alerta.ciclo:
            quando = f"ciclo até {alerta.ciclo.data_fim:%d/%m/%Y}"
        else:
            quando = f"gerado em {timezone.localtime(alerta.data_geracao):%d/%m/%Y}"
        rotulo = f"{alerta.get_tipo_display()} · {quando}"
        return rotulo if alerta.ativo else f"{rotulo} (não vale mais)"

    def clean_data(self):
        data = self.cleaned_data["data"]
        if data > timezone.localdate():
            raise forms.ValidationError("A data não pode ser futura.")
        return data


class DesfechoForm(forms.ModelForm):
    """Registra ou atualiza o desfecho; é o único campo editável depois (NF009)."""

    class Meta:
        model = Intervencao
        fields = ["desfecho"]

    def __init__(self, *args, autor, **kwargs):
        super().__init__(*args, **kwargs)
        self.autor = autor
        # is_valid() altera self.instance; guardar o valor original antes.
        self._anterior = self.instance.desfecho
        campo = self.fields["desfecho"]
        campo.required = True
        campo.choices = [c for c in campo.choices if c[0] != ""]

    def save(self, commit=True):
        with transaction.atomic():
            intervencao = super().save()
            registrar_alteracoes(
                autor=self.autor, objeto=intervencao, anteriores={"desfecho": self._anterior}
            )
        return intervencao
