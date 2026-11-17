"""Relatório dos alunos beneficiados por auxílios (RF021, SM #80, opção A). Só o Diretor.

Nada é gravado: a planilha de matrículas é lida na memória, o relatório é calculado na hora e
descartado com a resposta. Sem `RegistroImportacao`, sem `PendenciaImportacao`, sem sessão, sem
log, sem arquivo em disco. Para o upload nem passar por arquivo temporário, a view troca o
tratador de upload por um só de memória e recusa corpo grande antes de lê-lo.
"""

import io

from django.core.files.uploadhandler import MemoryFileUploadHandler
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, csrf_protect

from ingestao.leitura import ArquivoInvalidoError, ler_tabela
from ingestao.modelos import gerar_modelo
from relatorios import auxilios

from .acesso import diretor_required
from .forms_auxilios import ERRO_TAMANHO, LIMITE_BYTES, RelatorioAuxiliosForm

FIXO = {"categorias": auxilios.CATEGORIAS, "desfechos": auxilios.DESFECHOS}


@diretor_required
@csrf_exempt  # o CSRF é verificado em `_relatorio`, depois de trocar o tratador de upload
def relatorio(request):
    if request.method == "POST":
        if int(request.META.get("CONTENT_LENGTH") or 0) > LIMITE_BYTES + 64 * 1024:
            contexto = {"form": RelatorioAuxiliosForm(), "erro": ERRO_TAMANHO, **FIXO}
            return render(request, "web/auxilios.html", contexto, status=400)
        request.upload_handlers = [MemoryFileUploadHandler(request)]
    return _relatorio(request)


@csrf_protect
def _relatorio(request):
    form = RelatorioAuxiliosForm(request.POST or None, request.FILES or None)
    contexto = {"form": form, **FIXO}
    if request.method == "POST" and form.is_valid():
        arquivo, ano = form.cleaned_data["arquivo"], form.cleaned_data["ano"]
        try:
            linhas = ler_tabela(io.BytesIO(arquivo.read()), arquivo.name, colunas=auxilios.COLUNAS)
        except ArquivoInvalidoError as erro:
            form.add_error("arquivo", str(erro))
        else:
            matriculas, recusadas = auxilios.matriculas_do_arquivo(linhas, ano)
            contexto["relatorio"] = auxilios.calcular(matriculas, recusadas, ano)
    return render(request, "web/auxilios.html", contexto)


@diretor_required
def modelo(request, formato):
    """Modelo com matrículas sintéticas (NF017)."""
    try:
        conteudo, tipo, nome = gerar_modelo(
            "modelo_beneficiados", list(auxilios.COLUNAS), auxilios.EXEMPLOS, formato
        )
    except ValueError:
        raise Http404 from None
    resposta = HttpResponse(conteudo, content_type=tipo)
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta
