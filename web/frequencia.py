"""Importação da frequência da catraca (RF003). Só o Diretor importa (RN013)."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render

from core.models import RegistroImportacao
from ingestao import frequencia
from ingestao.modelos import TIPO_XLSX
from ingestao.planilhas_casd import ABA_PRESENCA
from inteligencia import alertas

from .acesso import diretor_required
from .forms_importacao import ImportacaoFrequenciaForm
from .importacao import executar_importacao, registrar_trilha


def _registrar(request, dados, nome, tamanho, resumo):
    """Trilha do upload e, com a frequência gravada, os alertas das semanas da grade (RF014)."""
    registrar_trilha(
        autor=request.user,
        tipo=RegistroImportacao.Tipo.FREQUENCIA,
        ano=dados["ano"],
        nome=nome,
        tamanho=tamanho,
        resumo=resumo,
    )
    alertas.gerar_frequencia_periodo(resumo.inicio, resumo.fim, dados["ano"])


@diretor_required
def frequencia_importar(request):
    """Conferir sempre antes de gravar (ver `web.importacao`). O arquivo nunca é persistido."""
    form = ImportacaoFrequenciaForm(request.POST or None, request.FILES or None)
    dados = form.is_valid() and form.cleaned_data
    aba = (dados["aba"] or ABA_PRESENCA) if dados else ""
    resultado = executar_importacao(
        request,
        form,
        colunas=None,
        parametros={"ano": dados["ano"], "aba": aba} if dados else {},
        ler=lambda arquivo, nome: frequencia.ler_grade(arquivo, nome, ano=dados["ano"], aba=aba),
        importar=lambda grade, gravar: frequencia.importar_frequencia(
            grade, ano=dados["ano"], autor=request.user, gravar=gravar
        ),
        registrar=lambda nome, tamanho, resumo: _registrar(request, dados, nome, tamanho, resumo),
    )
    contexto = {"form": form, "resultado": resultado, "resumo": resultado.resumo}
    return render(request, "web/frequencia_importar.html", contexto)


@login_required
def frequencia_modelo(request, formato):
    """Grade no layout real, com linhas sintéticas. Só .xlsx: a grade tem várias linhas de
    cabeçalho e uma coluna por dia."""
    if formato != "xlsx":
        raise Http404
    resposta = HttpResponse(frequencia.exemplo(date.today().year), content_type=TIPO_XLSX)
    resposta["Content-Disposition"] = 'attachment; filename="modelo_presenca_anual.xlsx"'
    return resposta
