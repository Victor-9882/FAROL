"""Ponte entre o banco e as funções de regra de `inteligencia.indicadores` (#18, #19).

Carrega em lote (poucas consultas, NF010) e devolve estruturas simples. As regras ficam todas
em `indicadores`; aqui só se busca, se agrupa e se aplica o calendário na hora (RN005).
"""

from collections import defaultdict
from datetime import date

from django.db.models import Q

from core.calendario import dias_letivos
from core.models import (
    Aluno,
    HistoricoTurma,
    RegistroFrequencia,
    ResultadoRedacao,
    ResultadoSimulado,
)

from . import indicadores as ind


def alunos_do_ano(ano: int, *, ate: date | None = None):
    """Alunos do ano letivo que entram nos indicadores: sem os lançados por engano e, com
    `ate`, só os que já tinham ingressado (RN004)."""
    qs = Aluno.objects.filter(turma__ano=ano).exclude(situacao=Aluno.Situacao.INVALIDO)
    if ate is not None:
        qs = qs.filter(data_ingresso__lte=ate)
    return qs.select_related("turma")


def frequencias(alunos, inicio: date, fim: date) -> dict[str, ind.Frequencia]:
    """Frequência de cada aluno de `inicio` a `fim` (RN001, RN002, RN004, RN005)."""
    alunos = list(alunos)
    letivos = set(dias_letivos(inicio, fim))
    dias = defaultdict(list)
    registros = RegistroFrequencia.objects.filter(
        aluno__in=alunos, data__gte=inicio, data__lte=fim
    ).values_list("aluno_id", "data", "presente", "justificada")
    for matricula, dia, presente, justificada in registros:
        dias[matricula].append(ind.Dia(dia, presente, justificada))
    return {
        a.pk: ind.frequencia(
            dias[a.pk], letivos=letivos, ingresso=a.data_ingresso, saida=a.data_saida
        )
        for a in alunos
    }


def turmas_na_data(alunos, dia: date) -> dict[str, int | None]:
    """Turma de cada aluno numa data, pelo histórico (RN011): `{matrícula: turma_id}`."""
    periodos = HistoricoTurma.objects.filter(aluno__in=list(alunos), data_inicio__lte=dia).filter(
        Q(data_fim__isnull=True) | Q(data_fim__gt=dia)
    )
    return dict(periodos.values_list("aluno_id", "turma_id"))


def historicos(alunos) -> dict[str, list[tuple[int, dict]]]:
    """Histórico de notas por ciclo de cada aluno: `{matrícula: [(ciclo, {área: nota})]}`."""
    resultados = defaultdict(list)
    linhas = ResultadoSimulado.objects.filter(aluno__in=list(alunos)).values_list(
        "aluno_id", "ciclo_id", "ciclo__data_inicio", "area", "presente", "nota_tri"
    )
    for matricula, ciclo, ordem, area, presente, nota in linhas:
        resultados[matricula].append(ind.Resultado(ciclo, ordem, area, presente, nota))
    return {m: ind.notas_por_ciclo(r) for m, r in resultados.items()}


def participacoes(alunos, inicio: date, fim: date) -> dict[str, ind.Participacao]:
    """Participação de cada aluno nas redações dos temas de `inicio` a `fim`."""
    entregas = defaultdict(list)
    linhas = ResultadoRedacao.objects.filter(
        aluno__in=list(alunos), tema_semana__gte=inicio, tema_semana__lte=fim
    ).values_list("aluno_id", "entregue")
    for matricula, entregue in linhas:
        entregas[matricula].append(entregue)
    return {m: ind.participacao(e) for m, e in entregas.items()}
