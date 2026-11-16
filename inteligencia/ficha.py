"""Dados da ficha longitudinal do aluno (RF011) e da comparação com o histórico e a turma
(RF013) (#21, #22). Só o Diretor vê (RN013).

- Desempenho por ciclo: nota TRI de cada área e a nota total, com o delta contra o último
  simulado em que o próprio aluno foi avaliado (RN008) e a classificação pelo limiar vigente.
- Média da turma no ciclo (turma da data, RN011): só como referência, nunca para classificar
  o aluno (RN008).
- Frequência por ciclo (RN001, RN002, RN004, RN005), redações, alertas e intervenções.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from core.models import Aluno, CicloCalendario, ResultadoSimulado

from . import consultas
from . import indicadores as ind
from .painel import limiar_desempenho

AREAS = ResultadoSimulado.Area


@dataclass
class LinhaCiclo:
    numero: int
    ciclo: CicloCalendario
    notas: dict = field(default_factory=dict)  # área -> nota ou None (faltou)
    deltas: dict = field(default_factory=dict)  # área -> Delta ou None
    total: Decimal | None = None
    delta_total: ind.Delta | None = None
    classificacao: str | None = None
    media_turma: Decimal | None = None
    frequencia: ind.Frequencia = field(default_factory=ind.Frequencia)
    avaliado: bool = False


def montar(aluno: Aluno) -> dict:
    ano = aluno.turma.ano
    ciclos = list(CicloCalendario.objects.filter(data_inicio__year=ano).order_by("data_inicio"))
    historico = consultas.historicos([aluno]).get(aluno.pk, [])
    notas = dict(historico)
    series = {area: ind.serie(historico, area) for area in AREAS.values}
    serie_total = ind.serie(historico)
    limiar = limiar_desempenho()
    colegas = list(consultas.alunos_do_ano(ano))
    historicos = consultas.historicos(colegas)
    linhas = []
    for numero, ciclo in enumerate(ciclos, 1):
        if ciclo.data_fim < aluno.data_ingresso:
            continue
        linha = LinhaCiclo(numero=numero, ciclo=ciclo)
        linha.frequencia = consultas.frequencias([aluno], ciclo.data_inicio, ciclo.data_fim)[
            aluno.pk
        ]
        if ciclo.pk in notas:
            linha.avaliado = True
            linha.notas = notas[ciclo.pk]
            linha.deltas = {a: ind.delta(series[a], ciclo.pk) for a in AREAS.values}
            linha.total = dict(serie_total).get(ciclo.pk)
            linha.delta_total = ind.delta(serie_total, ciclo.pk)
            if limiar is not None and linha.delta_total:
                linha.classificacao = ind.classificar(linha.delta_total.valor, limiar)
            turmas = consultas.turmas_na_data(colegas, ciclo.data_fim)
            mesma = [c for c in colegas if turmas.get(c.pk) == turmas.get(aluno.pk)]
            linha.media_turma = ind.media(
                dict(ind.serie(historicos.get(c.pk, []))).get(ciclo.pk) for c in mesma
            )
        linhas.append(linha)
    inicio = min((c.data_inicio for c in ciclos), default=aluno.data_ingresso)
    fim = max((c.data_fim for c in ciclos), default=aluno.data_ingresso)
    return {
        "linhas": linhas,
        "avaliadas": [linha for linha in linhas if linha.avaliado],
        "frequencia_ano": consultas.frequencias([aluno], inicio, fim)[aluno.pk],
        "redacoes": aluno.redacoes.order_by("-tema_semana"),
        "participacao": ind.participacao(aluno.redacoes.values_list("entregue", flat=True)),
        "alertas": aluno.alertas.select_related("ciclo", "regra").order_by("-data_geracao"),
        "intervencoes": aluno.intervencoes.select_related("usuario").order_by("-data"),
        "historico_turmas": aluno.historico_turmas.select_related("turma").order_by("data_inicio"),
        "limiar": limiar,
        "areas": AREAS.choices,
    }
