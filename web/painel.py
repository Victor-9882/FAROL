"""Painel inicial (RF010) e indicadores agregados (RF012) (#23, #20).

- Painel: alertas ativos da última semana com frequência e do último ciclo com simulado, e a
  situação de cada turma nesse ciclo. O Diretor clica numa contagem e vê a lista (RN013:
  dados nominais só para ele); o Membro vê só as contagens. Alertas a um clique da tela
  inicial e a ficha a dois (NF002).
- Indicadores: evolução por ciclo de cada turma, com filtros de turma, área e ciclo; visão
  agregada, sem nome, para o Diretor e o Membro.
"""

from django.http import Http404
from django.shortcuts import render

from core.models import Alerta, ResultadoSimulado, Turma
from inteligencia import painel

from . import graficos
from .acesso import diretor_required

AREAS = dict(ResultadoSimulado.Area.choices)


def _ano(request) -> int | None:
    valor = request.GET.get("ano", "")
    return int(valor) if valor.isdigit() else None


def inicio(request):
    ref = painel.referencia(_ano(request))
    turmas, total = painel.situacao(ref)
    alertas = painel.alertas_ativos(ref)
    contexto = {
        "ref": ref,
        "turmas": turmas,
        "total": total,
        "categorias": painel.CATEGORIAS,
        "alertas_frequencia": alertas[Alerta.Tipo.FREQUENCIA],
        "alertas_desempenho": alertas[Alerta.Tipo.DESEMPENHO],
        "ultimas": painel.ultimas_importacoes(),
        "limiar": painel.limiar_desempenho(),
    }
    return render(request, "web/painel.html", contexto)


@diretor_required
def painel_lista(request, categoria):
    """Lista nominal de uma contagem do painel: alertas de um tipo ou alunos de uma categoria,
    opcionalmente de uma turma. Só o Diretor (RN013)."""
    ref = painel.referencia(_ano(request))
    turma = request.GET.get("turma", "")
    if categoria in ("FREQUENCIA", "DESEMPENHO"):
        alertas = painel.alertas_ativos(ref)[categoria]
        if turma:
            alertas = [a for a in alertas if a.aluno.turma.nome == turma]
        titulo = dict(Alerta.Tipo.choices)[categoria]
        return render(
            request,
            "web/painel_lista.html",
            {"ref": ref, "titulo": f"Alertas: {titulo}", "alertas": alertas, "turma": turma},
        )
    if categoria not in painel.CATEGORIAS:
        raise Http404
    turmas, total = painel.situacao(ref)
    linha = next((t for t in turmas if t.turma == turma), None) if turma else total
    if linha is None:
        raise Http404
    contexto = {
        "ref": ref,
        "titulo": painel.CATEGORIAS[categoria],
        "alunos": sorted(linha.alunos[categoria], key=lambda a: a.nome),
        "turma": turma,
    }
    return render(request, "web/painel_lista.html", contexto)


def indicadores(request):
    """Indicadores agregados (RF012), sem dado nominal: qualquer usuário autenticado."""
    ref = painel.referencia(_ano(request))
    turmas = Turma.objects.filter(ano=ref.ano).order_by("nome")
    turma_id = request.GET.get("turma", "")
    turma_id = int(turma_id) if turma_id.isdigit() else None
    if turma_id and not turmas.filter(pk=turma_id).exists():
        raise Http404
    area = request.GET.get("area", "") or None
    if area and area not in AREAS:
        raise Http404
    ciclos, series = painel.evolucao(ref.ano, turma_id=turma_id, area=area)
    numeros = {c.pk: n for n, c in enumerate(ciclos, 1)}
    escolhido = request.GET.get("ciclo", "")
    ciclo = next((c for c in ciclos if str(c.pk) == escolhido), None)
    rotulos = [f"C{numeros[c.pk]}" for c in ciclos]
    nome_area = AREAS.get(area, "média das quatro áreas")
    contexto = {
        "ref": ref,
        "turmas": turmas,
        "areas": AREAS,
        "filtros": {"turma": turma_id, "area": area or "", "ciclo": ciclo.pk if ciclo else ""},
        "ciclos": ciclos,
        "numeros": numeros,
        "series": series,
        "ciclo": ciclo,
        "indice": ciclos.index(ciclo) if ciclo else None,
        "nome_area": nome_area,
        "grafico_nota": graficos.linhas(
            rotulos,
            {n: [p.nota for p in pts] for n, pts in series.items()},
            titulo=f"Nota TRI média por ciclo ({nome_area})",
        ),
        "grafico_presenca": graficos.linhas(
            rotulos,
            {n: [p.presenca for p in pts] for n, pts in series.items()},
            titulo="Presença por ciclo (%)",
            unidade="%",
        ),
    }
    if ciclo:
        contexto["detalhe"] = [(n, pts[contexto["indice"]]) for n, pts in series.items()]
    return render(request, "web/indicadores.html", contexto)
