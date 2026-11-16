"""Importação dos resultados de redações do Corrija-me (RF005). Só o Diretor importa (RN013)."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render

from core.models import RegistroImportacao
from ingestao import redacoes
from ingestao.modelos import TIPO_XLSX

from .acesso import diretor_required
from .forms_importacao import ImportacaoRedacoesForm
from .importacao import executar_importacao, registrar_trilha


@diretor_required
def redacoes_importar(request):
    """Conferir sempre antes de gravar (ver `web.importacao`). O arquivo nunca é persistido."""
    form = ImportacaoRedacoesForm(request.POST or None, request.FILES or None)
    dados = form.is_valid() and form.cleaned_data
    resultado = executar_importacao(
        request,
        form,
        colunas=redacoes.COLUNAS,
        opcionais=redacoes.OPCIONAIS,
        parametros={"ano": dados["ano"], "terca": dados["terca"].isoformat()} if dados else {},
        importar=lambda linhas, gravar: redacoes.importar_redacoes(
            linhas, ano=dados["ano"], terca=dados["terca"], autor=request.user, gravar=gravar
        ),
        registrar=lambda nome, tamanho, resumo: registrar_trilha(
            autor=request.user,
            tipo=RegistroImportacao.Tipo.REDACOES,
            ano=dados["ano"],
            nome=nome,
            tamanho=tamanho,
            resumo=resumo,
        ),
    )
    contexto = {"form": form, "resultado": resultado, "resumo": resultado.resumo}
    return render(request, "web/redacoes_importar.html", contexto)


@login_required
def redacoes_modelo(request, formato):
    """Exportação do Corrija-me no layout real, com redações sintéticas. Só .xlsx."""
    if formato != "xlsx":
        raise Http404
    resposta = HttpResponse(redacoes.exemplo(date.today().year), content_type=TIPO_XLSX)
    resposta["Content-Disposition"] = 'attachment; filename="modelo_corrija_me.xlsx"'
    return resposta
