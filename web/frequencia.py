"""Importação da frequência da catraca (RF003). Só o Diretor importa (RN013)."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render

from core.models import RegistroImportacao
from ingestao import frequencia
from ingestao.modelos import gerar_modelo

from .acesso import diretor_required
from .forms_importacao import ImportacaoFrequenciaForm
from .importacao import executar_importacao, registrar_trilha


@diretor_required
def frequencia_importar(request):
    """Conferir sempre antes de gravar (ver `web.importacao`). O arquivo nunca é persistido."""
    form = ImportacaoFrequenciaForm(request.POST or None, request.FILES or None)
    dados = form.is_valid() and form.cleaned_data
    parametros = (
        {
            "ano": dados["ano"],
            "inicio": dados["inicio"].isoformat(),
            "fim": dados["fim"].isoformat(),
        }
        if dados
        else {}
    )
    resultado = executar_importacao(
        request,
        form,
        colunas=frequencia.COLUNAS,
        opcionais=frequencia.OPCIONAIS,
        parametros=parametros,
        limite_linhas=frequencia.limite_linhas(),
        importar=lambda linhas, gravar: frequencia.importar_frequencia(
            linhas,
            ano=dados["ano"],
            inicio=dados["inicio"],
            fim=dados["fim"],
            autor=request.user,
            gravar=gravar,
        ),
        registrar=lambda nome, tamanho, resumo: registrar_trilha(
            autor=request.user,
            tipo=RegistroImportacao.Tipo.FREQUENCIA,
            ano=dados["ano"],
            nome=nome,
            tamanho=tamanho,
            resumo=resumo,
        ),
    )
    contexto = {"form": form, "resultado": resultado, "resumo": resultado.resumo}
    return render(request, "web/frequencia_importar.html", contexto)


@login_required
def frequencia_modelo(request, formato):
    ano = date.today().year
    try:
        conteudo, mime, nome = gerar_modelo(
            "modelo_catraca", list(frequencia.COLUNAS), frequencia.exemplos(ano), formato
        )
    except ValueError:
        raise Http404 from None
    resposta = HttpResponse(conteudo, content_type=mime)
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta
