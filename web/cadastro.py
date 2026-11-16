"""Views de cadastro de alunos e turmas (RF006).

Leitura (listas e detalhe da turma): Diretor e Membro, por decisão do usuário (nomes
visíveis ao Membro). Escrita (novo, editar, importar): só o Diretor. Não há exclusão (NF007).
"""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.auditoria import historico_de
from core.models import Aluno, Turma
from ingestao.cadastro import COLUNAS, EXEMPLOS, importar_cadastro
from ingestao.leitura import ArquivoInvalidoError, ler_tabela
from ingestao.modelos import gerar_modelo

from .acesso import diretor_required
from .forms_cadastro import AlunoEdicaoForm, AlunoNovoForm, ImportacaoCadastroForm, TurmaForm


def _inteiro(valor):
    return int(valor) if valor and str(valor).isdigit() else None


@login_required
def alunos(request):
    ano = _inteiro(request.GET.get("ano")) or Turma.objects.aggregate(a=Max("ano"))["a"]
    situacao = request.GET.get("situacao", "")
    qs = Aluno.objects.select_related("turma")
    if ano:
        qs = qs.filter(turma__ano=ano)
    turma = _inteiro(request.GET.get("turma"))
    if turma:
        qs = qs.filter(turma_id=turma)
    if situacao in Aluno.Situacao.values:
        qs = qs.filter(situacao=situacao)
    elif situacao != "TODAS":
        qs = qs.exclude(situacao=Aluno.Situacao.INVALIDO)
    contexto = {
        "alunos": qs,
        "ano": ano,
        "turma_filtro": turma,
        "situacao": situacao,
        "turmas": Turma.objects.filter(ano=ano) if ano else Turma.objects.none(),
        "situacoes": Aluno.Situacao.choices,
    }
    return render(request, "web/alunos.html", contexto)


@diretor_required
def aluno_novo(request):
    form = AlunoNovoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("web:alunos")
    return render(request, "web/aluno_form.html", {"form": form, "alvo": None})


@diretor_required
def aluno_editar(request, matricula):
    alvo = get_object_or_404(Aluno, pk=matricula)
    form = AlunoEdicaoForm(request.POST or None, instance=alvo, autor=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("web:alunos")
    contexto = {"form": form, "alvo": alvo, "historico": historico_de(alvo)}
    return render(request, "web/aluno_form.html", contexto)


@login_required
def turmas(request):
    lista = Turma.objects.annotate(total=Count("alunos"))
    return render(request, "web/turmas.html", {"turmas": lista})


@login_required
def turma_detalhe(request, pk):
    turma = get_object_or_404(Turma, pk=pk)
    contexto = {"turma": turma, "alunos": turma.alunos.exclude(situacao="INVALIDO")}
    return render(request, "web/turma_detalhe.html", contexto)


@diretor_required
def turma_nova(request):
    form = TurmaForm(request.POST or None, autor=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("web:turmas")
    return render(request, "web/turma_form.html", {"form": form, "alvo": None})


@diretor_required
def turma_editar(request, pk):
    alvo = get_object_or_404(Turma, pk=pk)
    form = TurmaForm(request.POST or None, instance=alvo, autor=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("web:turmas")
    contexto = {"form": form, "alvo": alvo, "historico": historico_de(alvo)}
    return render(request, "web/turma_form.html", contexto)


@diretor_required
def cadastro_importar(request):
    """Um formulário, dois botões: `conferir` (simula) e `importar` (grava). O arquivo é
    reenviado no segundo clique; nada fica em sessão nem em disco."""
    form = ImportacaoCadastroForm(request.POST or None, request.FILES or None)
    resumo, gravado = None, False
    if request.method == "POST" and form.is_valid():
        gravado = request.POST.get("acao") == "importar"
        arquivo = form.cleaned_data["arquivo"]
        try:
            linhas = ler_tabela(arquivo, arquivo.name, colunas=COLUNAS)
        except ArquivoInvalidoError as erro:
            form.add_error("arquivo", str(erro))
        else:
            with transaction.atomic():
                resumo = importar_cadastro(
                    linhas,
                    ano=form.cleaned_data["ano"],
                    autor=request.user,
                    data_mudanca=form.cleaned_data["data_mudanca"],
                    gravar=gravado,
                )
    return render(
        request,
        "web/cadastro_importar.html",
        {"form": form, "resumo": resumo, "gravado": gravado},
    )


def _modelo(formato):
    conteudo, tipo, nome = gerar_modelo("modelo_cadastro_alunos", list(COLUNAS), EXEMPLOS, formato)
    resposta = HttpResponse(conteudo, content_type=tipo)
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta


@diretor_required
def cadastro_modelo_xlsx(request):
    return _modelo("xlsx")


@diretor_required
def cadastro_modelo_csv(request):
    return _modelo("csv")
