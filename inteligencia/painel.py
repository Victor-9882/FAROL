"""Números do painel inicial (RF010) e dos indicadores agregados (RF012) (#23, #20).

Tudo é calculado na hora, a partir dos registros importados, com as regras de
`inteligencia.indicadores` e o limiar da regra vigente. A turma de cada aluno é a da data
(fim do ciclo) pelo histórico (RN011). Aqui não há nome nem matrícula nas saídas agregadas;
as listas nominais (`alunos` de cada categoria) só são mostradas ao Diretor (RN013).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Max

from core.models import (
    Alerta,
    CicloCalendario,
    RegistroFrequencia,
    RegistroImportacao,
    ResultadoSimulado,
    Turma,
)
from inteligencia.models import RegraAlerta

from . import consultas
from . import indicadores as ind
from .regras import vigente

LIMIAR_SEM_REGRA = None  # sem regra de desempenho ativa, não há classificação

CATEGORIAS = {
    "queda": "Queda de desempenho",
    "estagnado": "Estagnados",
    "evolucao": "Em evolução",
    "sem_avaliacao": "Sem avaliação no ciclo",
    "inativos": "Sem presença no ciclo",
}


@dataclass
class Referencia:
    """O período que o painel mostra: o ano, a última semana com frequência e o último ciclo
    com resultados de simulado (o ciclo "corrente" para os dados já importados)."""

    ano: int
    semana: date | None = None
    ciclo: CicloCalendario | None = None
    numero_ciclo: int | None = None

    @property
    def inicio(self) -> date | None:
        if self.ciclo:
            return self.ciclo.data_inicio
        return self.semana

    @property
    def semanas_alerta(self) -> tuple[date, date] | None:
        """Semanas dos alertas de frequência no painel: do início do ciclo de referência (ou
        da semana anterior, sem ciclo) até a última semana com frequência."""
        if self.semana is None:
            return None
        if self.ciclo:
            inicio = self.ciclo.data_inicio - timedelta(days=self.ciclo.data_inicio.weekday())
        else:
            inicio = self.semana - timedelta(days=7)
        return min(inicio, self.semana), self.semana

    @property
    def fim(self) -> date | None:
        if self.ciclo:
            return self.ciclo.data_fim
        return self.semana + timedelta(days=6) if self.semana else None


@dataclass
class Situacao:
    """Situação de uma turma (ou do total) no período de referência."""

    turma: str
    frequencia: ind.Frequencia = field(default_factory=ind.Frequencia)
    participacao: ind.Participacao = field(default_factory=ind.Participacao)
    alunos: dict[str, list] = field(default_factory=lambda: {c: [] for c in CATEGORIAS})
    total_alunos: int = 0

    def contagem(self, categoria) -> int:
        return len(self.alunos[categoria])


def referencia(ano: int | None = None) -> Referencia:
    """Ano com dados mais recente (ou o pedido), última semana com frequência e último ciclo
    com simulado desse ano."""
    if ano is None:
        candidatos = [
            RegistroFrequencia.objects.aggregate(d=Max("data"))["d"],
            ResultadoSimulado.objects.aggregate(d=Max("ciclo__data_fim"))["d"],
        ]
        candidatos = [d.year for d in candidatos if d]
        ano = (
            max(candidatos)
            if candidatos
            else (Turma.objects.aggregate(a=Max("ano"))["a"] or date.today().year)
        )
    ref = Referencia(ano=ano)
    ultima = RegistroFrequencia.objects.filter(data__year=ano).aggregate(d=Max("data"))["d"]
    if ultima:
        ref.semana = ultima - timedelta(days=ultima.weekday())
    ciclos = list(CicloCalendario.objects.filter(data_inicio__year=ano).order_by("data_inicio"))
    com_resultado = set(
        ResultadoSimulado.objects.filter(ciclo__in=ciclos).values_list("ciclo_id", flat=True)
    )
    for numero, ciclo in enumerate(ciclos, 1):
        if ciclo.pk in com_resultado:
            ref.ciclo, ref.numero_ciclo = ciclo, numero
    return ref


def limiar_desempenho() -> Decimal | None:
    regra = vigente(RegraAlerta.Tipo.DESEMPENHO)
    return regra.limiar if regra else LIMIAR_SEM_REGRA


def situacao(ref: Referencia) -> tuple[list[Situacao], Situacao]:
    """Situação por turma e o total, no período de referência (RF010)."""
    total = Situacao(turma="Total")
    if ref.inicio is None:
        return [], total
    alunos = list(consultas.alunos_do_ano(ref.ano, ate=ref.fim))
    turmas = consultas.turmas_na_data(alunos, ref.fim)
    nomes = dict(Turma.objects.filter(ano=ref.ano).values_list("pk", "nome"))
    frequencias = consultas.frequencias(alunos, ref.inicio, ref.fim)
    participacoes = consultas.participacoes(alunos, ref.inicio, ref.fim)
    historicos = consultas.historicos(alunos) if ref.ciclo else {}
    limiar = limiar_desempenho()
    por_turma: dict[str, Situacao] = {}
    for aluno in alunos:
        nome = nomes.get(turmas.get(aluno.pk) or aluno.turma_id, aluno.turma.nome)
        linha = por_turma.setdefault(nome, Situacao(turma=nome))
        f = frequencias[aluno.pk]
        p = participacoes.get(aluno.pk, ind.Participacao())
        categorias = []
        if f.dias and not (f.presencas + f.justificadas):
            categorias.append("inativos")
        if ref.ciclo:
            d = ind.delta(ind.serie(historicos.get(aluno.pk, [])), ref.ciclo.pk)
            classe = ind.classificar(d.valor if d else None, limiar) if limiar else None
            categorias.append(
                {ind.QUEDA: "queda", ind.EVOLUCAO: "evolucao", ind.ESTAGNADO: "estagnado"}.get(
                    classe, "sem_avaliacao"
                )
            )
        for alvo in (linha, total):
            alvo.total_alunos += 1
            alvo.frequencia += f
            alvo.participacao = ind.Participacao(
                alvo.participacao.registradas + p.registradas,
                alvo.participacao.entregues + p.entregues,
            )
            for categoria in categorias:
                alvo.alunos[categoria].append(aluno)
    return [por_turma[n] for n in sorted(por_turma)], total


def alertas_ativos(ref: Referencia) -> dict[str, list[Alerta]]:
    """Alertas ativos das semanas e do ciclo de referência, por tipo (NF004: tipo e motivo)."""
    base = Alerta.objects.filter(ativo=True, aluno__turma__ano=ref.ano).select_related(
        "aluno", "aluno__turma", "regra"
    )
    return {
        Alerta.Tipo.FREQUENCIA: list(
            base.filter(
                tipo=Alerta.Tipo.FREQUENCIA,
                semana__gte=ref.semanas_alerta[0],
                semana__lte=ref.semanas_alerta[1],
            ).order_by("-semana", "aluno__nome")
        )
        if ref.semana
        else [],
        Alerta.Tipo.DESEMPENHO: list(base.filter(tipo=Alerta.Tipo.DESEMPENHO, ciclo=ref.ciclo))
        if ref.ciclo
        else [],
    }


def ultimas_importacoes() -> list[tuple[str, date]]:
    """Data e hora da última importação de cada tipo (para "sem dados no período")."""
    ultimas = RegistroImportacao.objects.values("tipo").annotate(quando=Max("criado_em"))
    rotulos = dict(RegistroImportacao.Tipo.choices)
    return sorted(((rotulos[u["tipo"]], u["quando"]) for u in ultimas), key=lambda i: i[0])


# --- Indicadores agregados (RF012) ---------------------------------------------------


@dataclass
class Ponto:
    """Um ciclo de uma turma: média TRI, presença, participação e classificações."""

    nota: Decimal | None = None
    presenca: Decimal | None = None
    participacao: Decimal | None = None
    avaliados: int = 0
    queda: int = 0
    evolucao: int = 0


def evolucao(ano: int, *, turma_id: int | None = None, area: str | None = None):
    """Série por ciclo de cada turma (e do total): `(ciclos, {turma: [Ponto por ciclo]})`.

    `area=None` usa a nota total (média das quatro áreas, RN010); a média da turma é só dos
    alunos avaliados no ciclo (RN009)."""
    ciclos = list(
        CicloCalendario.objects.filter(data_inicio__year=ano, simulados__isnull=False)
        .distinct()
        .order_by("data_inicio")
    )
    todos = list(consultas.alunos_do_ano(ano))
    historicos = consultas.historicos(todos)
    nomes = dict(Turma.objects.filter(ano=ano).values_list("pk", "nome"))
    limiar = limiar_desempenho()
    series: dict[str, list[Ponto]] = defaultdict(lambda: [Ponto() for _ in ciclos])
    for indice, ciclo in enumerate(ciclos):
        alunos = [a for a in todos if a.data_ingresso <= ciclo.data_fim]
        turmas = consultas.turmas_na_data(alunos, ciclo.data_fim)
        if turma_id:
            alunos = [a for a in alunos if turmas.get(a.pk) == turma_id]
        frequencias = consultas.frequencias(alunos, ciclo.data_inicio, ciclo.data_fim)
        participacoes = consultas.participacoes(alunos, ciclo.data_inicio, ciclo.data_fim)
        grupos: dict[str, list] = defaultdict(list)
        for aluno in alunos:
            grupos[nomes.get(turmas.get(aluno.pk), aluno.turma.nome)].append(aluno)
            grupos["Total"].append(aluno)
        for nome, grupo in grupos.items():
            notas, deltas_ = [], []
            for aluno in grupo:
                valores = ind.serie(historicos.get(aluno.pk, []), area)
                notas.append(dict(valores).get(ciclo.pk))
                d = ind.delta(valores, ciclo.pk)
                deltas_.append(ind.classificar(d.valor if d else None, limiar) if limiar else None)
            f = ind.somar(frequencias[a.pk] for a in grupo)
            p = [participacoes.get(a.pk, ind.Participacao()) for a in grupo]
            series[nome][indice] = Ponto(
                nota=ind.media(notas),
                presenca=f.percentual,
                participacao=ind.Participacao(
                    sum(x.registradas for x in p), sum(x.entregues for x in p)
                ).percentual,
                avaliados=sum(1 for n in notas if n is not None),
                queda=deltas_.count(ind.QUEDA),
                evolucao=deltas_.count(ind.EVOLUCAO),
            )
    ordem = sorted(n for n in series if n != "Total") + (["Total"] if "Total" in series else [])
    return ciclos, {n: series[n] for n in ordem}
