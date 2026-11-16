"""Funções de regra dos indicadores (RF012, RF013): puras, sem tela nem banco (#18, #19).

Recebem dados já carregados (`inteligencia.consultas` faz a ponte com o ORM) e devolvem
números e classificações. Cada decisão de regra está aqui, coberta por testes:

Frequência
- RN005: só contam os dias de `letivos` (o calendário na hora do cálculo).
- RN004: só os dias entre o ingresso e a saída do aluno.
- RN001: falta é o dia letivo sem presença na catraca.
- RN002: a ausência justificada e aprovada conta como presença.

Desempenho
- RN010: a nota é a TRI por área; a nota total é a média das quatro áreas.
- RN009: área em que o aluno faltou não é avaliada naquele ciclo; a nota total só existe
  com as quatro áreas.
- RN008: o delta é contra o próprio histórico do aluno: a nota do ciclo menos a do último
  ciclo anterior em que ele foi avaliado. Sem ciclo anterior (primeiro simulado), não há delta.
- Classificação pelo delta e pelo limiar da regra vigente: queda se delta <= -limiar,
  evolução se delta >= +limiar, estagnado entre os dois.

Redação
- Participação: redações entregues sobre as redações registradas (entregues e não entregues).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

AREAS = ("LINGUAGENS", "HUMANAS", "NATUREZA", "MATEMATICA")
UMA_CASA = Decimal("0.1")

QUEDA, ESTAGNADO, EVOLUCAO = "QUEDA", "ESTAGNADO", "EVOLUCAO"
ROTULOS = {QUEDA: "Queda", ESTAGNADO: "Estagnado", EVOLUCAO: "Evolução"}


# --- Frequência (#18) ----------------------------------------------------------------


@dataclass(frozen=True)
class Dia:
    """Um registro de frequência: o dia e o que a catraca e a Direção disseram."""

    data: date
    presente: bool
    justificada: bool = False


@dataclass(frozen=True)
class Frequencia:
    dias: int = 0
    presencas: int = 0
    justificadas: int = 0
    faltas: int = 0  # não justificadas (RN001)

    @property
    def taxa(self) -> Decimal | None:
        """Presença com as justificadas (RN002), de 0 a 1; None sem dias."""
        if not self.dias:
            return None
        return Decimal(self.presencas + self.justificadas) / Decimal(self.dias)

    @property
    def percentual(self) -> Decimal | None:
        if self.taxa is None:
            return None
        return (self.taxa * 100).quantize(UMA_CASA, rounding=ROUND_HALF_UP)

    def __add__(self, outra: "Frequencia") -> "Frequencia":
        return Frequencia(
            self.dias + outra.dias,
            self.presencas + outra.presencas,
            self.justificadas + outra.justificadas,
            self.faltas + outra.faltas,
        )


def no_curso(dia: date, ingresso: date, saida: date | None) -> bool:
    """RN004: o aluno conta do ingresso até a saída (inclusive)."""
    return ingresso <= dia and (saida is None or dia <= saida)


def frequencia(
    dias: Iterable[Dia], *, letivos: set[date], ingresso: date, saida: date | None = None
) -> Frequencia:
    """Frequência de um aluno nos dias dados, aplicando RN001, RN002, RN004 e RN005."""
    contagem = Frequencia()
    for dia in dias:
        if dia.data not in letivos or not no_curso(dia.data, ingresso, saida):
            continue
        if dia.presente:
            contagem += Frequencia(1, 1, 0, 0)
        elif dia.justificada:
            contagem += Frequencia(1, 0, 1, 0)
        else:
            contagem += Frequencia(1, 0, 0, 1)
    return contagem


def somar(frequencias: Iterable[Frequencia]) -> Frequencia:
    total = Frequencia()
    for item in frequencias:
        total += item
    return total


# --- Desempenho (#19) ----------------------------------------------------------------


@dataclass(frozen=True)
class Resultado:
    """O resultado de um aluno numa área de um simulado (ciclo)."""

    ciclo: int  # identificador do ciclo
    ordem: date  # início do ciclo, para ordenar o histórico
    area: str
    presente: bool
    nota: Decimal | None


@dataclass(frozen=True)
class Delta:
    ciclo: int
    atual: Decimal
    anterior: Decimal
    ciclo_anterior: int

    @property
    def valor(self) -> Decimal:
        return self.atual - self.anterior


def notas_por_ciclo(resultados: Iterable[Resultado]) -> list[tuple[int, dict[str, Decimal | None]]]:
    """Histórico ordenado: `[(ciclo, {área: nota ou None se faltou})]` (RN009)."""
    por_ciclo: dict[int, tuple[date, dict]] = {}
    for r in resultados:
        _, areas = por_ciclo.setdefault(r.ciclo, (r.ordem, {}))
        areas[r.area] = r.nota if r.presente else None
    return [(c, areas) for c, (_, areas) in sorted(por_ciclo.items(), key=lambda i: i[1][0])]


def nota_total(areas: Mapping[str, Decimal | None]) -> Decimal | None:
    """Média TRI das quatro áreas (RN010); None se faltar alguma (RN009)."""
    notas = [areas.get(a) for a in AREAS]
    if any(n is None for n in notas):
        return None
    return (sum(notas) / Decimal(len(AREAS))).quantize(UMA_CASA, rounding=ROUND_HALF_UP)


def serie(historico: Sequence[tuple[int, Mapping]], area: str | None = None):
    """`[(ciclo, nota)]` de uma área, ou da nota total com `area=None`."""
    return [(c, nota_total(a) if area is None else a.get(area)) for c, a in historico]


def delta(valores: Sequence[tuple[int, Decimal | None]], ciclo: int) -> Delta | None:
    """Delta do `ciclo` contra o último ciclo anterior avaliado (RN008).

    None se o aluno não foi avaliado no ciclo (RN009) ou não tem ciclo anterior avaliado
    (primeiro simulado: sem base de comparação)."""
    anterior = None
    for c, nota in valores:
        if c == ciclo:
            if nota is None or anterior is None:
                return None
            return Delta(ciclo, nota, anterior[1], anterior[0])
        if nota is not None:
            anterior = (c, nota)
    return None


def deltas(valores: Sequence[tuple[int, Decimal | None]]) -> dict[int, Delta | None]:
    return {c: delta(valores, c) for c, _ in valores}


def classificar(variacao: Decimal | None, limiar: Decimal) -> str | None:
    """RN008: queda se a variação <= -limiar; evolução se >= +limiar; senão estagnado.
    None sem variação (RN009 ou primeiro simulado)."""
    if variacao is None:
        return None
    if variacao <= -limiar:
        return QUEDA
    if variacao >= limiar:
        return EVOLUCAO
    return ESTAGNADO


def media(notas: Iterable[Decimal | None]) -> Decimal | None:
    """Média das notas avaliadas (para a referência da turma, RF013); None se não há."""
    validas = [n for n in notas if n is not None]
    if not validas:
        return None
    return (sum(validas) / Decimal(len(validas))).quantize(UMA_CASA, rounding=ROUND_HALF_UP)


# --- Redação (#19) -------------------------------------------------------------------


@dataclass(frozen=True)
class Participacao:
    registradas: int = 0
    entregues: int = 0

    @property
    def taxa(self) -> Decimal | None:
        if not self.registradas:
            return None
        return Decimal(self.entregues) / Decimal(self.registradas)

    @property
    def percentual(self) -> Decimal | None:
        if self.taxa is None:
            return None
        return (self.taxa * 100).quantize(UMA_CASA, rounding=ROUND_HALF_UP)


def participacao(entregas: Iterable[bool]) -> Participacao:
    """Redações registradas e entregues; `entregas` traz `entregue` de cada registro."""
    lista = list(entregas)
    return Participacao(len(lista), sum(1 for e in lista if e))
