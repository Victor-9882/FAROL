"""Calendário letivo, ciclos e temas (RF007, RN005, RN006, RN007). Dados sintéticos de 2026."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core import calendario as cal
from core.models import CicloCalendario, DiaCalendario, PeriodoLetivo, TemaRedacao

D = date


def _dias(inicio, fim, letivo=True, descricao=""):
    d = inicio
    while d <= fim:
        DiaCalendario.objects.create(data=d, letivo=letivo, descricao=descricao)
        d += timedelta(days=1)


@pytest.fixture
def calendario_2026(db):
    """Dois períodos (férias de julho entre eles) e exceções: Carnaval e um sábado com aula."""
    PeriodoLetivo.objects.create(inicio=D(2026, 2, 2), fim=D(2026, 7, 3))
    PeriodoLetivo.objects.create(inicio=D(2026, 7, 20), fim=D(2026, 12, 11))
    _dias(D(2026, 2, 16), D(2026, 2, 17), letivo=False, descricao="Carnaval")
    _dias(D(2026, 3, 7), D(2026, 3, 7), letivo=True, descricao="Sábado com aula")


@pytest.mark.regras
def test_feriado_nao_e_dia_letivo(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 2, 16)) is False
    assert cal.eh_dia_letivo(D(2026, 2, 17)) is False


@pytest.mark.regras
def test_vespera_e_dia_seguinte_sao_letivos(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 2, 13)) is True
    assert cal.eh_dia_letivo(D(2026, 2, 18)) is True


@pytest.mark.regras
def test_dia_util_no_periodo_sem_registro_e_letivo(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 2, 3)) is True  # terça comum


@pytest.mark.regras
def test_fim_de_semana_nao_e_letivo(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 2, 14)) is False  # sábado
    assert cal.eh_dia_letivo(D(2026, 2, 15)) is False  # domingo


@pytest.mark.regras
def test_sabado_com_aula_e_letivo(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 3, 7)) is True


@pytest.mark.regras
def test_recesso_limites(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 7, 3)) is True
    assert cal.eh_dia_letivo(D(2026, 7, 6)) is False
    assert cal.eh_dia_letivo(D(2026, 7, 17)) is False
    assert cal.eh_dia_letivo(D(2026, 7, 20)) is True


@pytest.mark.regras
def test_dia_fora_dos_periodos_nao_e_letivo(db):
    assert cal.eh_dia_letivo(D(2026, 2, 3)) is False  # sem período cadastrado


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
def test_dias_letivos_segue_a_mesma_regra(calendario_2026):
    # semana do sábado com aula e semana do recesso
    assert cal.dias_letivos(D(2026, 3, 2), D(2026, 3, 8)) == [
        D(2026, 3, d) for d in (2, 3, 4, 5, 6, 7)
    ]
    assert cal.dias_letivos(D(2026, 7, 1), D(2026, 7, 21)) == [
        D(2026, 7, 1),
        D(2026, 7, 2),
        D(2026, 7, 3),
        D(2026, 7, 20),
        D(2026, 7, 21),
    ]
    for dia in cal.dias_letivos(D(2026, 2, 1), D(2026, 12, 31)):
        assert cal.eh_dia_letivo(dia)


@pytest.mark.regras
def test_dia_que_vira_nao_letivo_deixa_de_contar(calendario_2026):
    assert cal.eh_dia_letivo(D(2026, 2, 18)) is True
    DiaCalendario.objects.create(data=D(2026, 2, 18), letivo=False)
    assert cal.eh_dia_letivo(D(2026, 2, 18)) is False


def test_periodos_nao_se_sobrepoem(calendario_2026):
    with pytest.raises(ValidationError):
        PeriodoLetivo(inicio=D(2026, 7, 3), fim=D(2026, 7, 10)).full_clean()
    PeriodoLetivo(inicio=D(2026, 7, 4), fim=D(2026, 7, 19)).full_clean()
    PeriodoLetivo.objects.get(inicio=D(2026, 2, 2)).full_clean()  # editar não conflita consigo


def test_periodo_fim_nao_antes_do_inicio(db):
    PeriodoLetivo(inicio=D(2026, 2, 2), fim=D(2026, 2, 2)).full_clean()
    with pytest.raises(ValidationError):
        PeriodoLetivo(inicio=D(2026, 2, 2), fim=D(2026, 2, 1)).full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        PeriodoLetivo.objects.bulk_create([PeriodoLetivo(inicio=D(2026, 2, 2), fim=D(2026, 2, 1))])


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


def test_tema_em_semana_sem_tema_devolve_none(db):
    t3 = TemaRedacao.objects.create(data=D(2026, 2, 3), tema="a")
    assert cal.tema_em(D(2026, 2, 9)) == t3  # segunda: último dia de validade
    assert cal.tema_em(D(2026, 2, 10)) is None  # terça seguinte sem tema lançado
    assert cal.tema_em(D(2026, 3, 3)) is None


def test_mensagens_das_restricoes_sao_legiveis(db):
    with pytest.raises(ValidationError) as erro:
        CicloCalendario(
            data_inicio=D(2026, 2, 2), data_fim=D(2026, 2, 15), data_simulado=D(2026, 2, 16)
        ).full_clean()
    assert "A data do simulado deve estar dentro do ciclo." in erro.value.messages
    with pytest.raises(ValidationError) as erro:
        TemaRedacao(data=D(2026, 2, 2), tema="x").full_clean()
    assert not any("foi violada" in m for m in erro.value.messages)


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
