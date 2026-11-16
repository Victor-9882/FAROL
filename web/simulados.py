"""Importação dos resultados de simulados do P+ (RF004). Só o Diretor importa (RN013)."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render

from core.models import RegistroImportacao
from ingestao import simulados
from ingestao.modelos import TIPO_XLSX

from .acesso import diretor_required
from .forms_importacao import ImportacaoSimuladosForm
from .importacao import executar_importacao, registrar_trilha


@diretor_required
def simulados_importar(request):
    """Conferir sempre antes de gravar (ver `web.importacao`). O arquivo nunca é persistido."""
    form = ImportacaoSimuladosForm(request.POST or None, request.FILES or None)
    dados = form.is_valid() and form.cleaned_data
    resultado = executar_importacao(
        request,
        form,
        colunas=None,
        parametros={"ano": dados["ano"], "ciclo": dados["ciclo"].pk} if dados else {},
        ler=simulados.ler_relatorio,
        importar=lambda linhas, gravar: simulados.importar_simulados(
            linhas, ano=dados["ano"], ciclo=dados["ciclo"], autor=request.user, gravar=gravar
        ),
        registrar=lambda nome, tamanho, resumo: registrar_trilha(
            autor=request.user,
            tipo=RegistroImportacao.Tipo.SIMULADOS,
            ano=dados["ano"],
            nome=nome,
            tamanho=tamanho,
            resumo=resumo,
        ),
    )
    contexto = {"form": form, "resultado": resultado, "resumo": resultado.resumo}
    return render(request, "web/simulados_importar.html", contexto)


@login_required
def simulados_modelo(request, formato):
    """Relatório do P+ no layout real (duas abas), com alunos sintéticos. Só .xlsx."""
    if formato != "xlsx":
        raise Http404
    resposta = HttpResponse(simulados.exemplo(date.today().year), content_type=TIPO_XLSX)
    resposta["Content-Disposition"] = 'attachment; filename="modelo_relatorio_pmais.xlsx"'
    return resposta
