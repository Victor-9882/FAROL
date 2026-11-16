"""Consultas do calendário letivo (RF007, RN005, RN006, RN007).

Dia letivo (RN005): segunda a sexta dentro de um período letivo, exceto os dias marcados
como não letivos; um dia marcado como letivo (sábado com aula) também conta. A regra é
aplicada na hora do cálculo, nunca só na importação.
"""

from datetime import date, timedelta

from .models import CicloCalendario, DiaCalendario, PeriodoLetivo, TemaRedacao

DURACAO_CICLO_DIAS = 14


def eh_dia_letivo(data: date) -> bool:
    """Segunda a sexta dentro de um `PeriodoLetivo`, salvo `DiaCalendario(letivo=False)`.

    `DiaCalendario(letivo=True)` é a exceção contrária (sábado com aula) e vale por si.
    """
    return data in set(dias_letivos(data, data))


def dias_letivos(inicio: date, fim: date) -> list[date]:
    """Dias letivos de `inicio` a `fim`, extremos inclusos, pela mesma regra de `eh_dia_letivo`."""
    if fim < inicio:
        return []
    periodos = list(
        PeriodoLetivo.objects.filter(inicio__lte=fim, fim__gte=inicio).values_list("inicio", "fim")
    )
    excecoes = dict(
        DiaCalendario.objects.filter(data__gte=inicio, data__lte=fim).values_list("data", "letivo")
    )
    dias = []
    for n in range((fim - inicio).days + 1):
        dia = inicio + timedelta(days=n)
        if dia in excecoes:
            letivo = excecoes[dia]
        else:
            letivo = dia.weekday() < 5 and any(i <= dia <= f for i, f in periodos)
        if letivo:
            dias.append(dia)
    return dias


def ciclo_em(data: date) -> CicloCalendario | None:
    return CicloCalendario.objects.filter(data_inicio__lte=data, data_fim__gte=data).first()


def tema_em(data: date) -> TemaRedacao | None:
    """Tema vigente: o lançado na terça anterior (vale de terça a segunda, RN007).

    Semana sem tema lançado devolve `None`."""
    return (
        TemaRedacao.objects.filter(data__gt=data - timedelta(days=7), data__lte=data)
        .order_by("-data")
        .first()
    )


def temas_do_ciclo(ciclo: CicloCalendario):
    return TemaRedacao.objects.filter(data__gte=ciclo.data_inicio, data__lte=ciclo.data_fim)


def aviso_duracao(inicio: date, fim: date) -> str:
    """Aviso (não erro) quando o ciclo não tem 14 dias; o calendário manda (RN006)."""
    dias = (fim - inicio).days + 1
    if dias == DURACAO_CICLO_DIAS:
        return ""
    return f"ciclo com {dias} dias (o usual é {DURACAO_CICLO_DIAS})"
