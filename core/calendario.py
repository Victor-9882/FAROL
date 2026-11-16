"""Consultas do calendário letivo (RF007, RN005, RN006, RN007).

A regra de dia letivo é aplicada na hora do cálculo, nunca só na importação: um dia pode
virar não letivo depois (RN005). Dia ausente do calendário (fim de semana, fora do
período) não é letivo.
"""

from datetime import date

from .models import CicloCalendario, DiaCalendario, TemaRedacao

DURACAO_CICLO_DIAS = 14


def eh_dia_letivo(data: date) -> bool:
    return DiaCalendario.objects.filter(data=data, letivo=True).exists()


def dias_letivos(inicio: date, fim: date) -> list[date]:
    """Dias letivos de `inicio` a `fim`, extremos inclusos."""
    return list(
        DiaCalendario.objects.filter(data__gte=inicio, data__lte=fim, letivo=True).values_list(
            "data", flat=True
        )
    )


def ciclo_em(data: date) -> CicloCalendario | None:
    return CicloCalendario.objects.filter(data_inicio__lte=data, data_fim__gte=data).first()


def tema_em(data: date) -> TemaRedacao | None:
    """Tema vigente: o último lançado até `data` (vale de terça a segunda)."""
    return TemaRedacao.objects.filter(data__lte=data).order_by("-data").first()


def temas_do_ciclo(ciclo: CicloCalendario):
    return TemaRedacao.objects.filter(data__gte=ciclo.data_inicio, data__lte=ciclo.data_fim)


def aviso_duracao(inicio: date, fim: date) -> str:
    """Aviso (não erro) quando o ciclo não tem 14 dias; o calendário manda (RN006)."""
    dias = (fim - inicio).days + 1
    if dias == DURACAO_CICLO_DIAS:
        return ""
    return f"ciclo com {dias} dias (o usual é {DURACAO_CICLO_DIAS})"
