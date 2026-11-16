"""Importação do cadastro de alunos e turmas (RF006, RN003, RN004, RN011, NF008)."""

from datetime import date
from pathlib import Path

import pytest

from core.models import Aluno, HistoricoTurma, RegistroAlteracao, Turma
from ingestao.cadastro import COLUNAS, importar_cadastro
from ingestao.leitura import ler_tabela

pytestmark = pytest.mark.django_db

PEQUENA = Path(__file__).parent / "dados_sinteticos" / "pequena" / "2026" / "cadastro_alunos.csv"
HOJE = date(2026, 3, 2)


def _linha(matricula="S1", nome="Ana Sintética", turma="Turma A", ingresso="02/02/2026", n=2):
    return {
        "matricula": matricula,
        "nome": nome,
        "turma": turma,
        "data_ingresso": ingresso,
        "_linha": n,
    }


def _importar(linhas, diretor, gravar=True, data_mudanca=HOJE):
    return importar_cadastro(
        linhas, ano=2026, autor=diretor, data_mudanca=data_mudanca, gravar=gravar
    )


def _pequena():
    with PEQUENA.open("rb") as f:
        return ler_tabela(f, PEQUENA.name, colunas=COLUNAS)


def test_importa_base_pequena_2026(diretor):
    r = _importar(_pequena(), diretor)
    assert (r.criados, r.turmas_criadas) == (20, 5)
    assert not r.divergencias and not r.inconsistentes
    assert Aluno.objects.count() == 20
    assert HistoricoTurma.objects.filter(data_fim__isnull=True).count() == 20


def test_reimportar_nao_duplica(diretor):
    _importar(_pequena(), diretor)
    r = _importar(_pequena(), diretor)
    assert (r.criados, r.sem_alteracao, r.turmas_criadas) == (0, 20, 0)
    assert Aluno.objects.count() == 20 and HistoricoTurma.objects.count() == 20


def test_conferir_nao_grava(diretor):
    r = _importar(_pequena(), diretor, gravar=False)
    assert (r.criados, r.turmas_criadas) == (20, 5)
    assert not Aluno.objects.exists() and not Turma.objects.exists()


def test_matricula_em_branco_e_inconsistente(diretor):
    r = _importar([_linha(matricula="  ")], diretor)
    assert r.inconsistentes[0][0] == 2 and not Aluno.objects.exists()


def test_matricula_repetida_no_arquivo(diretor):
    r = _importar([_linha(n=2), _linha(nome="Outra Pessoa", n=3)], diretor)
    assert r.criados == 1 and r.inconsistentes[0][0] == 3


def test_nome_divergente_nao_sobrescreve(diretor, turma_a):
    Aluno.objects.create(
        matricula="S1", nome="Ana Sintética", data_ingresso=date(2026, 2, 2), turma=turma_a
    )
    r = _importar([_linha(nome="Beatriz Outra", turma="Turma B")], diretor)
    assert len(r.divergencias) == 1 and r.mudancas_turma == 0
    aluno = Aluno.objects.get(pk="S1")
    assert aluno.nome == "Ana Sintética" and aluno.turma == turma_a
    assert not Turma.objects.filter(nome="Turma B").exists()
    assert "Beatriz" not in str(r.divergencias)


def test_nome_so_difere_em_caixa_acento_espaco_nao_diverge(diretor, turma_a):
    Aluno.objects.create(
        matricula="S1", nome="Ana Sintética", data_ingresso=date(2026, 2, 2), turma=turma_a
    )
    r = _importar([_linha(nome="  ANA   sintetica ")], diretor)
    assert not r.divergencias and r.sem_alteracao == 1


def test_data_ingresso_divergente_nao_sobrescreve(diretor, turma_a):
    Aluno.objects.create(
        matricula="S1", nome="Ana Sintética", data_ingresso=date(2026, 2, 2), turma=turma_a
    )
    r = _importar([_linha(ingresso="09/02/2026")], diretor)
    assert len(r.divergencias) == 1
    assert Aluno.objects.get(pk="S1").data_ingresso == date(2026, 2, 2)


def test_turma_diferente_muda_turma_e_preserva_historico(diretor, turma_a):
    Aluno.objects.create(
        matricula="S1", nome="Ana Sintética", data_ingresso=date(2026, 2, 2), turma=turma_a
    )
    r = _importar([_linha(turma="Turma B")], diretor)
    assert r.mudancas_turma == 1 and r.turmas_criadas == 1
    periodos = list(HistoricoTurma.objects.filter(aluno="S1").order_by("data_inicio"))
    assert len(periodos) == 2 and periodos[0].data_fim == HOJE
    assert periodos[1].data_inicio == HOJE and periodos[1].data_fim is None
    reg = RegistroAlteracao.objects.get(campo="turma")
    assert reg.autor == diretor and reg.objeto_id == "S1"


def test_mudanca_na_data_de_inicio_e_inconsistente_e_no_dia_seguinte_passa(diretor, turma_a):
    Aluno.objects.create(
        matricula="S1", nome="Ana Sintética", data_ingresso=date(2026, 2, 2), turma=turma_a
    )
    r = _importar([_linha(turma="Turma B")], diretor, data_mudanca=date(2026, 2, 2))
    assert len(r.inconsistentes) == 1 and r.mudancas_turma == 0
    r = _importar([_linha(turma="Turma B")], diretor, data_mudanca=date(2026, 2, 3))
    assert r.mudancas_turma == 1


@pytest.mark.parametrize("ingresso", ["31/02/2026", "", "ontem"])
def test_data_invalida(diretor, ingresso):
    r = _importar([_linha(ingresso=ingresso)], diretor)
    assert len(r.inconsistentes) == 1 and not Aluno.objects.exists()


def test_turma_reaproveitada_sem_diferenciar_caixa(diretor, turma_a):
    r = _importar([_linha(turma="  turma   a ")], diretor)
    assert r.turmas_criadas == 0 and Turma.objects.count() == 1
    assert Aluno.objects.get(pk="S1").turma == turma_a


@pytest.mark.parametrize(("tam", "ok"), [(20, True), (21, False)])
def test_limite_matricula(diretor, tam, ok):
    r = _importar([_linha(matricula="S" * tam)], diretor)
    assert (r.criados == 1) is ok and (len(r.inconsistentes) == 0) is ok


@pytest.mark.parametrize(("tam", "ok"), [(150, True), (151, False)])
def test_limite_nome(diretor, tam, ok):
    r = _importar([_linha(nome="N" * tam)], diretor)
    assert (r.criados == 1) is ok


def test_importacao_nao_altera_situacao(diretor, turma_a):
    Aluno.objects.create(
        matricula="S1",
        nome="Ana Sintética",
        data_ingresso=date(2026, 2, 2),
        turma=turma_a,
        situacao="EVADIDO",
        data_saida=date(2026, 5, 1),
    )
    _importar([_linha()], diretor)
    assert Aluno.objects.get(pk="S1").situacao == "EVADIDO"
