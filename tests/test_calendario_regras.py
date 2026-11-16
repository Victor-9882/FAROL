"""Calendário letivo, ciclos e temas (RF007, RN005, RN006, RN007). Dados sintéticos de 2026."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core import calendario as cal
from core.models import CicloCalendario, DiaCalendario, TemaRedacao

D = date


def _dias(inicio, fim, letivo=True, descricao=""):
    d = inicio
    while d <= fim:
        DiaCalendario.objects.create(data=d, letivo=letivo, descricao=descricao)
        d += timedelta(days=1)


@pytest.fixture
def calendario_2026(db):
    _dias(D(2026, 2, 2), D(2026, 2, 13))
    _dias(D(2026, 2, 16), D(2026, 2, 17), letivo=False, descricao="Carnaval")
    _dias(D(2026, 2, 18), D(2026, 2, 20))
    _dias(D(2026, 6, 29), D(2026, 7, 3))
    _dias(D(2026, 7, 6), D(2026, 7, 17), letivo=False, descricao="Recesso")
    _dias(D(2026, 7, 20), D(2026, 7, 24))


@pytest.mark.regras
def test_feriado_nao_e_dia_letivo(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 2, 16)) is False
    assert cal.eh_dia_letivo(D(2026, 2, 17)) is False


@pytest.mark.regras
def test_vespera_e_dia_seguinte_sao_letivos(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 2, 13)) is True
    assert cal.eh_dia_letivo(D(2026, 2, 18)) is True


@pytest.mark.regras
def test_recesso_limites(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 7, 3)) is True
    assert cal.eh_dia_letivo(D(2026, 7, 6)) is False
    assert cal.eh_dia_letivo(D(2026, 7, 17)) is False
    assert cal.eh_dia_letivo(D(2026, 7, 20)) is True


@pytest.mark.regras
def test_dia_fora_do_calendario_nao_e_letivo(db):
    assert cal.eh_dia_letivo(D(2026, 2, 14)) is False


@pytest.mark.regras
def test_dias_letivos_inclui_extremos(calendario_2026):
    assert cal.dias_letivos(D(2026, 2, 16), D(2026, 2, 20)) == [
        D(2026, 2, 18),
        D(2026, 2, 19),
        D(2026, 2, 20),
    ]
    assert cal.dias_letivos(D(2026, 2, 18), D(2026, 2, 18)) == [D(2026, 2, 18)]
    assert cal.dias_letivos(D(2026, 2, 16), D(2026, 2, 16)) == []


@pytest.mark.regras
def test_dia_que_vira_nao_letivo_deixa_de_contar(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 2, 18)) is True
    DiaCalendario.objects.filter(data=D(2026, 2, 18)).update(letivo=False)
    assert cal.eh_dia_letivo(D(2026, 2, 18)) is False


@pytest.fixture
def ciclos(db):
    c1 = CicloCalendario.objects.create(data_inicio=D(2026, 2, 2), data_fim=D(2026, 2, 15))
    c2 = CicloCalendario.objects.create(data_inicio=D(2026, 2, 16), data_fim=D(2026, 3, 1))
    return c1, c2


def test_ciclo_em_limites(ciclos):
    c1, c2 = ciclos
    assert cal.ciclo_em(D(2026, 2, 1)) is None
    assert cal.ciclo_em(D(2026, 2, 2)) == c1
    assert cal.ciclo_em(D(2026, 2, 15)) == c1
    assert cal.ciclo_em(D(2026, 2, 16)) == c2
    assert cal.ciclo_em(D(2026, 3, 2)) is None  # lacuna (recesso)


def test_ciclos_nao_se_sobrepoem(ciclos):
    with pytest.raises(ValidationError):
        CicloCalendario(data_inicio=D(2026, 2, 15), data_fim=D(2026, 2, 20)).full_clean()
    CicloCalendario(data_inicio=D(2026, 3, 2), data_fim=D(2026, 3, 15)).full_clean()


def test_ciclo_editar_nao_conflita_consigo(ciclos):
    c1, _ = ciclos
    c1.full_clean()


def test_simulado_dentro_do_ciclo(db):
    ini, fim = D(2026, 2, 2), D(2026, 2, 15)
    for ok in (ini, fim, None):
        CicloCalendario(data_inicio=ini, data_fim=fim, data_simulado=ok).full_clean()
    for ruim in (ini - timedelta(days=1), fim + timedelta(days=1)):
        with pytest.raises(ValidationError):
            CicloCalendario(data_inicio=ini, data_fim=fim, data_simulado=ruim).full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CicloCalendario.objects.bulk_create(
                [CicloCalendario(data_inicio=ini, data_fim=fim, data_simulado=ruim)]
            )


def test_duracao_diferente_de_14_dias_gera_aviso(db):
    ini = D(2026, 2, 2)
    assert cal.aviso_duracao(ini, ini + timedelta(days=13)) == ""
    assert cal.aviso_duracao(ini, ini + timedelta(days=12)) != ""
    assert cal.aviso_duracao(ini, ini + timedelta(days=14)) != ""


def test_tema_so_na_terca(db):
    with pytest.raises(ValidationError):
        TemaRedacao(data=D(2026, 2, 2), tema="x").full_clean()
    TemaRedacao(data=D(2026, 2, 3), tema="x").full_clean()
    with pytest.raises(ValidationError):
        TemaRedacao(data=D(2026, 2, 4), tema="x").full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        TemaRedacao.objects.bulk_create([TemaRedacao(data=D(2026, 2, 2), tema="x")])


def test_tema_em_limites(db):
    t3 = TemaRedacao.objects.create(data=D(2026, 2, 3), tema="a")
    t10 = TemaRedacao.objects.create(data=D(2026, 2, 10), tema="b")
    assert cal.tema_em(D(2026, 2, 9)) == t3
    assert cal.tema_em(D(2026, 2, 10)) == t10
    assert cal.tema_em(D(2026, 2, 2)) is None


def test_tema_em_terca_de_feriado_e_aceito(db):
    DiaCalendario.objects.create(data=D(2026, 2, 17), letivo=False)
    TemaRedacao(data=D(2026, 2, 17), tema="x").full_clean()


def test_temas_do_ciclo(ciclos):
    c1, c2 = ciclos
    TemaRedacao.objects.create(data=D(2026, 2, 3), tema="a")
    TemaRedacao.objects.create(data=D(2026, 2, 10), tema="b")
    TemaRedacao.objects.create(data=D(2026, 2, 17), tema="c")
    assert [t.tema for t in cal.temas_do_ciclo(c1)] == ["a", "b"]
    assert [t.tema for t in cal.temas_do_ciclo(c2)] == ["c"]
