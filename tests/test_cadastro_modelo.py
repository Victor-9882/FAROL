"""Situação do aluno, ingressados_ate e corrigir_ingresso (RF006, RN004, RN011)."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import Aluno

pytestmark = pytest.mark.django_db
D = date(2026, 2, 9)


def _aluno(turma, matricula="S1", **kw):
    return Aluno.objects.create(
        matricula=matricula, nome="Aluno Sintético", data_ingresso=D, turma=turma, **kw
    )


def test_ingressados_ate_inclui_o_dia_e_exclui_a_vespera(turma_a):
    _aluno(turma_a)
    assert Aluno.objects.ingressados_ate(D).count() == 1
    assert Aluno.objects.ingressados_ate(D - timedelta(days=1)).count() == 0


def test_corrigir_ingresso_ajusta_primeiro_periodo(turma_a):
    a = _aluno(turma_a)
    a.corrigir_ingresso(D - timedelta(days=3))
    a.refresh_from_db()
    assert a.data_ingresso == D - timedelta(days=3)
    assert a.historico_turmas.get().data_inicio == D - timedelta(days=3)


def test_corrigir_ingresso_limite_do_fim_do_primeiro_periodo(turma_a):
    from core.models import Turma

    a = _aluno(turma_a)
    fim = D + timedelta(days=10)
    a.mudar_turma(Turma.objects.create(nome="Turma B", ano=2026), fim)
    a.corrigir_ingresso(fim - timedelta(days=1))
    with pytest.raises(ValueError):
        a.corrigir_ingresso(fim)
    a.refresh_from_db()
    assert a.data_ingresso == fim - timedelta(days=1)


def test_ativos_exclui_os_demais(turma_a):
    _aluno(turma_a, "S1")
    _aluno(turma_a, "S2", situacao="DESLIGADO", data_saida=D)
    _aluno(turma_a, "S3", situacao="INVALIDO")
    assert list(Aluno.objects.ativos().values_list("pk", flat=True)) == ["S1"]


def test_saida_no_dia_do_ingresso_passa_e_antes_e_rejeitada(turma_a):
    a = _aluno(turma_a, situacao="EVADIDO", data_saida=D)
    a.full_clean()
    a.data_saida = D - timedelta(days=1)
    with pytest.raises(ValidationError):
        a.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        a.save()


def test_ativo_com_data_saida_e_rejeitado(turma_a):
    a = _aluno(turma_a)
    a.data_saida = D
    with pytest.raises(ValidationError):
        a.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        a.save()


def test_desligado_exige_data_e_invalido_nao(turma_a):
    a = _aluno(turma_a, situacao="DESLIGADO")
    with pytest.raises(ValidationError):
        a.full_clean()
    b = _aluno(turma_a, "S2", situacao="INVALIDO")
    b.full_clean()
