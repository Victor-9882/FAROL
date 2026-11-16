"""Histórico de intervenções (RF020, NF007, RN013).

Só o Diretor: a tela traz nome, matrícula e descrição livre. Cobre todos os anos e gestões,
inclusive alunos não ativos e usuários revogados. Somente leitura: sem editar nem excluir.
"""

from django.core.paginator import Paginator
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.models import Intervencao

from .acesso import diretor_required
from .forms_intervencoes import FiltroIntervencoesForm

POR_PAGINA = 50


@diretor_required
@require_GET
def historico(request):
    params = request.GET.copy()
    params.pop("pagina", None)
    form = FiltroIntervencoesForm(params)
    if form.is_valid():
        qs = form.aplicar(
            Intervencao.objects.select_related("aluno", "aluno__turma", "usuario", "alerta")
        ).order_by("-data", "-id")
    else:
        qs = Intervencao.objects.none()
    pagina = Paginator(qs, POR_PAGINA).get_page(request.GET.get("pagina"))
    return render(
        request,
        "web/intervencoes.html",
        {"form": form, "pagina": pagina, "consulta": params.urlencode()},
    )
