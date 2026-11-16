"""Tela de pendências de importação: associar a um aluno ou descartar (RN003, NF009).

Só o Diretor: as pendências trazem a matrícula e o nome informados (RN013). O nome é só
verificação; se difere do cadastro, a associação pede confirmação explícita. As mensagens
de sucesso ou erro, que podem ir para o cookie de mensagens, nunca trazem nome nem
matrícula; o nome do cadastro só aparece na própria página, na confirmação.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from core.models import Aluno, PendenciaImportacao
from ingestao.pendencias import NOME_DIVERGENTE, AssociacaoRecusada, associar, descartar

from .acesso import diretor_required

POR_PAGINA = 100
Situacao = PendenciaImportacao.Situacao


def _filtros(params):
    origem = params.get("origem", "")
    situacao = params.get("situacao", Situacao.PENDENTE)
    ano = params.get("ano", "")
    qs = PendenciaImportacao.objects.select_related("aluno")
    if origem in PendenciaImportacao.Origem.values:
        qs = qs.filter(origem=origem)
    if situacao in Situacao.values:
        qs = qs.filter(situacao=situacao)
    if ano.isdigit():
        qs = qs.filter(ano=int(ano))
    return qs, {"origem": origem, "situacao": situacao, "ano": ano}


def _processar(request):
    """Aplica a ação do POST. Devolve o contexto de confirmação de nome, ou None."""
    ids = [i for i in request.POST.getlist("pendencia") if i.isdigit()]
    selecionadas = list(PendenciaImportacao.objects.filter(pk__in=ids, situacao=Situacao.PENDENTE))
    if not selecionadas:
        messages.error(request, "Selecione ao menos uma pendência ainda pendente.")
        return None
    if request.POST.get("acao") == "descartar":
        n = descartar(selecionadas, autor=request.user)
        messages.success(request, f"{n} pendência(s) descartada(s).")
        return None
    aluno = Aluno.objects.filter(pk=request.POST.get("matricula", "").strip()).first()
    if aluno is None:
        messages.error(request, "Nenhum aluno do cadastro tem a matrícula informada.")
        return None
    try:
        associadas, recusas = associar(
            selecionadas,
            aluno,
            autor=request.user,
            confirmar_nome=request.POST.get("confirmar_nome") == "1",
        )
    except AssociacaoRecusada as erro:
        if str(erro) == NOME_DIVERGENTE:
            return {"aluno": aluno, "selecionadas": {p.pk for p in selecionadas}}
        messages.error(request, f"Associação recusada: {erro}.")
        return None
    if associadas:
        messages.success(request, f"{associadas} pendência(s) associada(s).")
    for _, motivo in recusas:
        messages.error(request, f"Uma pendência não foi associada: {motivo}.")
    return None


@diretor_required
def pendencias(request):
    qs, filtros = _filtros(request.GET)
    confirmacao = None
    if request.method == "POST":
        confirmacao = _processar(request)
        if confirmacao is None:
            return redirect(request.get_full_path())
    pagina = Paginator(qs, POR_PAGINA).get_page(request.GET.get("pagina"))
    contexto = {
        "pagina": pagina,
        "filtros": filtros,
        "origens": PendenciaImportacao.Origem.choices,
        "situacoes": Situacao.choices,
        "confirmacao": confirmacao,
        "matricula": request.POST.get("matricula", "") if confirmacao else "",
    }
    return render(request, "web/pendencias.html", contexto)
