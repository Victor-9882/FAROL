"""Views do calendário letivo, dos ciclos e dos temas de redação (RF007).

Leitura: qualquer usuário autenticado (sem dado pessoal). Importar e editar: só o Diretor,
com auditoria (NF009). Não há exclusão (NF007). Baixar modelos: qualquer autenticado.
"""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.auditoria import historico_de
from core.calendario import dias_letivos
from core.models import (
    CicloCalendario,
    DiaCalendario,
    PeriodoLetivo,
    RegistroImportacao,
    TemaRedacao,
)
from ingestao.calendario import TIPOS
from ingestao.modelos import gerar_modelo

from .acesso import diretor_required
from .forms_calendario import FORMULARIOS, ImportacaoCalendarioForm
from .importacao import executar_importacao


def _tipo(slug):
    try:
        return TIPOS[slug]
    except KeyError:
        raise Http404 from None


@login_required
def calendario(request):
    ano = request.GET.get("ano", "")
    ano = int(ano) if ano.isdigit() else None
    if ano is None:
        datas = [
            PeriodoLetivo.objects.aggregate(a=Max("inicio"))["a"],
            CicloCalendario.objects.aggregate(a=Max("data_inicio"))["a"],
            DiaCalendario.objects.aggregate(a=Max("data"))["a"],
            TemaRedacao.objects.aggregate(a=Max("data"))["a"],
        ]
        datas = [d for d in datas if d]
        ano = max(datas).year if datas else None
    contexto = {"ano": ano, "periodos": [], "ciclos": [], "nao_letivos": [], "temas": []}
    if ano:
        temas = list(TemaRedacao.objects.filter(data__year=ano))
        for numero, ciclo in enumerate(CicloCalendario.objects.filter(data_inicio__year=ano), 1):
            ciclo.numero = numero
            ciclo.temas = [t for t in temas if ciclo.data_inicio <= t.data <= ciclo.data_fim]
            contexto["ciclos"].append(ciclo)
        contexto["periodos"] = PeriodoLetivo.objects.filter(inicio__year=ano)
        contexto["nao_letivos"] = DiaCalendario.objects.filter(data__year=ano, letivo=False)
        contexto["excecoes_letivas"] = DiaCalendario.objects.filter(data__year=ano, letivo=True)
        contexto["temas"] = temas
        contexto["total_letivos"] = len(dias_letivos(date(ano, 1, 1), date(ano, 12, 31)))
    return render(request, "web/calendario.html", contexto)


@diretor_required
def calendario_importar(request):
    """Conferir sempre antes de gravar (ver `web.importacao`). O arquivo nunca é persistido."""
    form = ImportacaoCalendarioForm(request.POST or None, request.FILES or None)
    dados = form.is_valid() and form.cleaned_data
    tipo = TIPOS[dados["tipo"]] if dados else None

    def registrar(nome, tamanho, resumo):
        RegistroImportacao.objects.create(
            autor=request.user,
            tipo=tipo.registro,
            nome_arquivo=nome,
            tamanho_bytes=tamanho,
            ano=dados["ano"],
            criados=resumo.criados,
            atualizados=resumo.atualizados,
            sem_alteracao=resumo.sem_alteracao,
            inconsistentes=len(resumo.inconsistentes),
        )

    resultado = executar_importacao(
        request,
        form,
        colunas=tipo.colunas if tipo else None,
        opcionais=tipo.opcionais if tipo else frozenset(),
        parametros={"tipo": dados["tipo"], "ano": dados["ano"]} if dados else {},
        importar=lambda linhas, gravar: tipo.importar(
            linhas, ano=dados["ano"], autor=request.user, gravar=gravar
        ),
        registrar=registrar,
    )
    contexto = {
        "form": form,
        "resultado": resultado,
        "resumo": resultado.resumo,
        "gravado": resultado.gravado,
        "tipos": TIPOS,
    }
    return render(request, "web/calendario_importar.html", contexto)


@login_required
def calendario_modelo(request, tipo, formato):
    t = _tipo(tipo)
    try:
        conteudo, mime, nome = gerar_modelo(f"modelo_{tipo}", list(t.colunas), t.exemplos, formato)
    except ValueError:
        raise Http404 from None
    resposta = HttpResponse(conteudo, content_type=mime)
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta


@diretor_required
def calendario_item(request, tipo, pk=None):
    """Novo (`pk` ausente) e edição de um dia, ciclo ou tema. Sem exclusão (NF007)."""
    t = _tipo(tipo)
    alvo = get_object_or_404(t.modelo, pk=pk) if pk is not None else None
    form = FORMULARIOS[tipo](request.POST or None, instance=alvo, autor=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        aviso = getattr(form, "aviso", "")
        if aviso:
            messages.warning(request, f"Salvo, mas há um aviso: {aviso}.")
        return redirect("web:calendario")
    contexto = {
        "form": form,
        "alvo": alvo,
        "rotulo": t.rotulo,
        "historico": historico_de(alvo) if alvo else [],
    }
    return render(request, "web/calendario_form.html", contexto)
