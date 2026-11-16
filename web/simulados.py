"""Importação dos resultados de simulados do P+ (RF004). Só o Diretor importa (RN013)."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render

from core.models import RegistroImportacao
from ingestao import simulados
from ingestao.modelos import gerar_modelo

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
        colunas=simulados.COLUNAS,
        opcionais=simulados.OPCIONAIS,
        parametros={"ano": dados["ano"]} if dados else {},
        importar=lambda linhas, gravar: simulados.importar_simulados(
            linhas, ano=dados["ano"], autor=request.user, gravar=gravar
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
    ano = date.today().year
    try:
        conteudo, mime, nome = gerar_modelo(
            "modelo_simulados", list(simulados.COLUNAS), simulados.exemplos(ano), formato
        )
    except ValueError:
        raise Http404 from None
    resposta = HttpResponse(conteudo, content_type=mime)
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta
