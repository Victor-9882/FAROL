"""Painel inicial (RF010) e indicadores agregados (RF012) (#23, #20).

- Painel: alertas ativos da última semana com frequência e do último ciclo com simulado, e a
  situação de cada turma nesse ciclo. O Diretor clica numa contagem e vê a lista (RN013:
  dados nominais só para ele); o Membro vê só as contagens. Alertas a um clique da tela
  inicial e a ficha a dois (NF002).
- Indicadores: evolução por ciclo de cada turma, com filtros de turma, área e ciclo; visão
  agregada, sem nome, para o Diretor e o Membro.
- O curso em quatro grupos de presença × notas (#92): contagens, plano, grupos por turma e
  distribuição por ciclo, com filtro de ciclo e de turma. O Membro vê os pontos sem nome nem
  link; a lista de cada grupo é só do Diretor (RN013).
"""

from urllib.parse import urlencode

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from core.models import Alerta, ResultadoSimulado, Turma
from inteligencia import grupos, painel

from . import graficos
from .acesso import diretor_required
from .templatetags.farol import indice, pontos

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
        "quadro": _quadro(request, ref),
    }
    return render(request, "web/painel.html", contexto)


# --- Quatro grupos (#92) -------------------------------------------------------------


def _filtros_grupos(request, ref):
    """Ciclo (padrão: o de referência) e turma escolhidos para os grupos.

    Devolve `(ciclos, numero, ciclo, turmas, turma_id)`, ou None sem ciclo com simulado.
    Turma de outro ano ou inexistente: 404, como nos indicadores."""
    ciclos = grupos.ciclos_com_simulado(ref.ano)
    if not ciclos:
        return None
    escolhido = request.GET.get("ciclo", "")
    padrao = ref.ciclo.pk if ref.ciclo else ciclos[-1][1].pk
    numero, ciclo = next(
        (item for item in ciclos if str(item[1].pk) == escolhido),
        next(item for item in ciclos if item[1].pk == padrao),
    )
    turmas = list(Turma.objects.filter(ano=ref.ano).order_by("nome"))
    valor = request.GET.get("turma", "")
    turma_id = int(valor) if valor.isdigit() else None
    if turma_id and turma_id not in {t.pk for t in turmas}:
        raise Http404
    return ciclos, numero, ciclo, turmas, turma_id


def _titulo_ponto(posicao, *, nominal: bool) -> str:
    """Texto do ponto no plano; nome só para o Diretor (RN013)."""
    quem = f"{posicao.aluno.nome} · " if nominal else ""
    presenca = posicao.frequencia.percentual
    return (
        f"{quem}{posicao.turma} · grupo {posicao.grupo}\n"
        f"Presença {presenca}% ({indice(posicao.presenca)}) · "
        f"Δ {pontos(posicao.delta)} pontos ({indice(posicao.notas)})"
    )


def _quadro(request, ref) -> dict | None:
    filtros = _filtros_grupos(request, ref)
    if filtros is None:
        return None
    ciclos, numero, ciclo, turmas, turma_id = filtros
    nominal = request.user.is_diretor
    todas = grupos.posicoes(ref.ano, ciclo)
    recorte = [p for p in todas if not turma_id or p.turma_id == turma_id]
    contagem = grupos.contar(p.grupo for p in recorte)
    total = sum(contagem[g] for g in grupos.GRUPOS)

    def parte(n, de):
        return round(100 * n / de) if de else 0

    pontos_plano = [
        {
            "presenca": p.presenca,
            "notas": p.notas,
            "grupo": p.grupo,
            "titulo": _titulo_ponto(p, nominal=nominal),
            "url": reverse("web:ficha", args=[p.aluno.pk]) if nominal else None,
            "apagado": bool(turma_id) and p.turma_id != turma_id,
        }
        for p in todas
        if p.grupo
    ]
    por_turma = []
    for nome in sorted({p.turma for p in todas}):
        c = grupos.contar(p.grupo for p in todas if p.turma == nome)
        n = sum(c[g] for g in grupos.GRUPOS)
        por_turma.append(
            {
                "nome": nome,
                "total": n,
                "segmentos": [
                    (g, c[g], parte(c[g], n), f"{100 * c[g] / n:.2f}")
                    for g in grupos.GRUPOS
                    if c[g]
                ],
            }
        )
    distribuicao = grupos.distribuicao(ref.ano, turma_id=turma_id)
    nome_turma = next((t.nome for t in turmas if t.pk == turma_id), "Curso todo")
    return {
        "ciclos": ciclos,
        "numero": numero,
        "ciclo": ciclo,
        "turmas": turmas,
        "turma_id": turma_id,
        "recorte": nome_turma,
        "query": urlencode(
            {"ano": ref.ano, "ciclo": ciclo.pk} | ({"turma": turma_id} if turma_id else {})
        ),
        "contagem": contagem,
        "total": total,
        "cartoes": [
            {"grupo": grupos.GRUPOS[g], "n": contagem[g], "parte": parte(contagem[g], total)}
            for g in (grupos.C, grupos.A, grupos.D, grupos.B)  # a posição no plano
        ],
        # O mesmo σ de `grupos.posicoes`: os Δ de todo o curso no ciclo, não só do recorte.
        "sigma": grupos.desvio_padrao(p.delta for p in todas if p.delta is not None),
        "plano": graficos.plano(
            pontos_plano,
            titulo=f"Presença × notas no ciclo {numero}: cada ponto é um aluno",
        ),
        "por_turma": por_turma,
        "grafico_distribuicao": graficos.distribuicao_grupos(
            [(f"C{n}", c) for n, _, c in distribuicao],
            titulo=f"Parte de cada grupo por ciclo ({nome_turma})",
            destaque=f"C{numero}",
        ),
    }


@diretor_required
def painel_grupo(request, letra):
    """Lista nominal de um grupo no ciclo e na turma escolhidos. Só o Diretor (RN013)."""
    if letra not in grupos.GRUPOS:
        raise Http404
    ref = painel.referencia(_ano(request))
    filtros = _filtros_grupos(request, ref)
    if filtros is None:
        raise Http404
    _, numero, ciclo, turmas, turma_id = filtros
    alunos = sorted(
        (
            p
            for p in grupos.posicoes(ref.ano, ciclo)
            if p.grupo == letra and (not turma_id or p.turma_id == turma_id)
        ),
        key=lambda p: (-p.distancia, p.aluno.nome),
    )
    contexto = {
        "ref": ref,
        "grupo": grupos.GRUPOS[letra],
        "numero": numero,
        "ciclo": ciclo,
        "recorte": next((t.nome for t in turmas if t.pk == turma_id), "Curso todo"),
        "alunos": alunos,
    }
    return render(request, "web/painel_grupo.html", contexto)


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
