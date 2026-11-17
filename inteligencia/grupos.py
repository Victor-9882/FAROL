"""O curso em quatro grupos de presença × notas (RF010, RF011, RF012) (#92).

Os dois índices vão de −1 a +1, com as contas do protótipo do PEI (`docs/prototipo/`):

- Presença na sede: `2 · taxa − 1`, como o SE do PEI. A taxa é a frequência do ciclo
  (RN001, RN002, RN004, RN005); 0% → −1, 50% → 0, 100% → +1.
- Notas nos simulados: `limitar(z / 2, −1, +1)`, como o SD do PEI, com `z = Δ / σ`. Δ é o
  delta da nota TRI média contra o último simulado em que o aluno foi avaliado (RN008), e σ é
  o desvio-padrão (populacional) dos Δ do curso no ciclo. ±1 equivale a dois desvios.

O zero de cada eixo separa os grupos. Não há limiar nem regra nova: o zero da presença é o
meio da escala, e o zero das notas é o próprio Δ. Quem faltou ao simulado (RN009), não tem
simulado anterior ou não tem dia letivo no ciclo fica fora dos grupos naquele ciclo.

Os rótulos só descrevem a posição (RN012): nenhum grupo sugere ação nem classifica o aluno.
As listas nominais de cada grupo são só do Diretor (RN013).
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from core.models import Aluno, CicloCalendario, Turma

from . import consultas
from . import indicadores as ind

A, B, C, D = "A", "B", "C", "D"


@dataclass(frozen=True)
class Grupo:
    letra: str
    nome: str
    presenca: str
    notas: str


PRESENCA_ACIMA, PRESENCA_ABAIXO = "Presença de 50% ou mais", "Presença abaixo de 50%"
NOTA_ACIMA, NOTA_ABAIXO = "Nota igual ou acima do último simulado", "Nota abaixo do último simulado"
GRUPOS = {
    A: Grupo(A, "Em dia", PRESENCA_ACIMA, NOTA_ACIMA),
    B: Grupo(B, "Nota abaixo", PRESENCA_ACIMA, NOTA_ABAIXO),
    C: Grupo(C, "Presença abaixo", PRESENCA_ABAIXO, NOTA_ACIMA),
    D: Grupo(D, "Ambas abaixo", PRESENCA_ABAIXO, NOTA_ABAIXO),
}


# --- Regras (puras) ------------------------------------------------------------------


def indice_presenca(taxa: Decimal | None) -> float | None:
    """`2 · taxa − 1`, de −1 a +1; None sem dia letivo no ciclo."""
    if taxa is None:
        return None
    return float(2 * taxa - 1)


def desvio_padrao(valores: Iterable[Decimal | float]) -> float | None:
    """Desvio-padrão populacional; None com menos de dois valores ou sem variação."""
    lista = [float(v) for v in valores]
    if len(lista) < 2:
        return None
    media = sum(lista) / len(lista)
    sigma = math.sqrt(sum((v - media) ** 2 for v in lista) / len(lista))
    return sigma or None


def indice_notas(delta: Decimal | None, sigma: float | None) -> float | None:
    """`limitar(z / 2, −1, +1)` com `z = Δ / σ`; None sem delta (RN009) ou sem σ."""
    if delta is None or not sigma:
        return None
    return max(-1.0, min(1.0, float(delta) / sigma / 2))


def grupo(presenca: float | None, notas: float | None) -> str | None:
    """A letra do grupo pelo zero de cada eixo; o zero conta como "igual ou acima"."""
    if presenca is None or notas is None:
        return None
    if presenca >= 0:
        return A if notas >= 0 else B
    return C if notas >= 0 else D


def sigma_do_ciclo(historicos: Mapping[str, Sequence], ciclo_id: int) -> float | None:
    """σ dos Δ da nota TRI média de todos os alunos avaliados no ciclo (RN008, RN009)."""
    deltas = (ind.delta(ind.serie(h), ciclo_id) for h in historicos.values())
    return desvio_padrao(d.valor for d in deltas if d is not None)


def contar(letras: Iterable[str | None]) -> dict[str, int]:
    """`{A: n, B: n, C: n, D: n, "fora": n}`."""
    contagem = {g: 0 for g in GRUPOS} | {"fora": 0}
    for letra in letras:
        contagem[letra or "fora"] += 1
    return contagem


# --- Banco ---------------------------------------------------------------------------


@dataclass
class Posicao:
    """Um aluno num ciclo: os valores de origem, os dois índices e o grupo."""

    aluno: Aluno
    turma_id: int | None
    turma: str
    frequencia: ind.Frequencia
    delta: Decimal | None
    presenca: float | None
    notas: float | None
    grupo: str | None

    @property
    def distancia(self) -> float:
        """Distância ao centro do plano, para ordenar as listas."""
        return math.hypot(self.presenca or 0, self.notas or 0)


def ciclos_com_simulado(ano: int) -> list[tuple[int, CicloCalendario]]:
    """`[(número, ciclo)]` dos ciclos do ano com simulado, numerados entre todos os ciclos do
    ano, como no painel e na ficha."""
    ciclos = CicloCalendario.objects.filter(data_inicio__year=ano).order_by("data_inicio")
    com_simulado = set(
        CicloCalendario.objects.filter(data_inicio__year=ano, simulados__isnull=False)
        .values_list("pk", flat=True)
        .distinct()
    )
    return [(n, c) for n, c in enumerate(ciclos, 1) if c.pk in com_simulado]


def _posicoes(alunos, historicos, ciclo, nomes) -> list[Posicao]:
    alunos = [a for a in alunos if a.data_ingresso <= ciclo.data_fim]
    turmas = consultas.turmas_na_data(alunos, ciclo.data_fim)
    frequencias = consultas.frequencias(alunos, ciclo.data_inicio, ciclo.data_fim)
    sigma = sigma_do_ciclo({a.pk: historicos.get(a.pk, []) for a in alunos}, ciclo.pk)
    resultado = []
    for aluno in alunos:
        d = ind.delta(ind.serie(historicos.get(aluno.pk, [])), ciclo.pk)
        f = frequencias[aluno.pk]
        presenca = indice_presenca(f.taxa)
        notas = indice_notas(d.valor if d else None, sigma)
        turma_id = turmas.get(aluno.pk) or aluno.turma_id
        resultado.append(
            Posicao(
                aluno=aluno,
                turma_id=turma_id,
                turma=nomes.get(turma_id, aluno.turma.nome),
                frequencia=f,
                delta=d.valor if d else None,
                presenca=presenca,
                notas=notas,
                grupo=grupo(presenca, notas),
            )
        )
    return resultado


def posicoes(ano: int, ciclo: CicloCalendario) -> list[Posicao]:
    """Posição de cada aluno do ano no ciclo. A turma é a da data (RN011)."""
    alunos = list(consultas.alunos_do_ano(ano))
    nomes = dict(Turma.objects.filter(ano=ano).values_list("pk", "nome"))
    return _posicoes(alunos, consultas.historicos(alunos), ciclo, nomes)


def distribuicao(ano: int, *, turma_id: int | None = None):
    """Contagem dos grupos em cada ciclo com simulado: `[(número, ciclo, contagem)]`."""
    alunos = list(consultas.alunos_do_ano(ano))
    historicos = consultas.historicos(alunos)
    nomes = dict(Turma.objects.filter(ano=ano).values_list("pk", "nome"))
    serie = []
    for numero, ciclo in ciclos_com_simulado(ano):
        pos = _posicoes(alunos, historicos, ciclo, nomes)
        if turma_id:
            pos = [p for p in pos if p.turma_id == turma_id]
        serie.append((numero, ciclo, contar(p.grupo for p in pos)))
    return serie
