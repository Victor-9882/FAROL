"""Histórico (RF020), registro (RF019) e desfecho de intervenções (NF007, NF009, RN012, RN013).

Só o Diretor: as telas trazem nome, matrícula e descrição livre. O histórico cobre todos os
anos e gestões, inclusive alunos não ativos e usuários revogados. Registrar uma intervenção
não altera aluno nem alerta (RN012). Depois de criada, só o desfecho muda, com auditoria;
não há exclusão. Aluno inválido não recebe intervenção; desligado e evadido recebem.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from core.models import Aluno, Intervencao

from .acesso import diretor_required
from .forms_intervencoes import DesfechoForm, FiltroIntervencoesForm, IntervencaoForm

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


@diretor_required
@require_http_methods(["GET", "POST"])
def nova(request, matricula):
    aluno = get_object_or_404(Aluno.objects.exclude(situacao=Aluno.Situacao.INVALIDO), pk=matricula)
    autor = request.user
    if request.method == "POST":
        form = IntervencaoForm(request.POST, aluno=aluno, autor=autor)
        if form.is_valid():
            form.save()
            messages.success(request, "Intervenção registrada.")
            return redirect("web:ficha", matricula=aluno.matricula)
    else:
        inicial = {
            "data": timezone.localdate(),
            "responsavel": autor.get_full_name() or autor.get_username(),
        }
        origem = request.GET.get("alerta", "")
        if origem.isdigit() and aluno.alertas.filter(pk=int(origem)).exists():
            inicial["alerta"] = int(origem)
        form = IntervencaoForm(initial=inicial, aluno=aluno, autor=autor)
    return render(request, "web/intervencao_form.html", {"form": form, "aluno": aluno})


@diretor_required
@require_http_methods(["GET", "POST"])
def desfecho(request, pk):
    intervencao = get_object_or_404(Intervencao.objects.select_related("aluno", "alerta"), pk=pk)
    if request.method == "POST":
        form = DesfechoForm(request.POST, instance=intervencao, autor=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Desfecho registrado.")
            return redirect("web:ficha", matricula=intervencao.aluno_id)
    else:
        form = DesfechoForm(instance=intervencao, autor=request.user)
    return render(
        request,
        "web/intervencao_desfecho.html",
        {"form": form, "intervencao": intervencao, "aluno": intervencao.aluno},
    )
