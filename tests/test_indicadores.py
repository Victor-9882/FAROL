"""Motores de indicadores de frequência, desempenho e participação (#18, #19).

As funções de regra são puras (sem banco); a integração usa a base sintética (NF017).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from inteligencia import indicadores as ind

SEG = date(2026, 3, 2)
SEMANA = {SEG + timedelta(days=n) for n in range(5)}
D = Decimal


def _dias(*codigos, inicio=SEG):
    """'P' presente, 'F' falta, 'J' justificada."""
    return [
        ind.Dia(inicio + timedelta(days=n), presente=c == "P", justificada=c == "J")
        for n, c in enumerate(codigos)
    ]


# --- Frequência (RN001, RN002, RN004, RN005) -----------------------------------------


@pytest.mark.regras
def test_rn001_e_rn002_falta_e_justificada():
    f = ind.frequencia(_dias("P", "F", "J", "P", "F"), letivos=SEMANA, ingresso=SEG)
    assert (f.dias, f.presencas, f.justificadas, f.faltas) == (5, 2, 1, 2)
    assert f.taxa == D(3) / D(5) and f.percentual == D("60.0")  # justificada conta (RN002)


@pytest.mark.regras
def test_rn005_dia_que_deixou_de_ser_letivo_nao_conta():
    letivos = SEMANA - {SEG + timedelta(days=1)}  # virou emenda depois da importação
    f = ind.frequencia(_dias("P", "F", "P", "P", "P"), letivos=letivos, ingresso=SEG)
    assert (f.dias, f.faltas) == (4, 0)


@pytest.mark.regras
def test_rn004_janela_do_aluno_nos_limites():
    dias = _dias("F", "F", "F", "F", "F")
    assert ind.frequencia(dias, letivos=SEMANA, ingresso=SEG + timedelta(days=2)).dias == 3
    saida = SEG + timedelta(days=1)
    assert ind.frequencia(dias, letivos=SEMANA, ingresso=SEG, saida=saida).dias == 2
    assert ind.no_curso(SEG, SEG, SEG) and not ind.no_curso(SEG, SEG + timedelta(days=1), None)


def test_frequencia_vazia_e_soma():
    vazia = ind.frequencia([], letivos=SEMANA, ingresso=SEG)
    assert vazia.taxa is None and vazia.percentual is None
    total = ind.somar([ind.Frequencia(5, 4, 0, 1), ind.Frequencia(5, 2, 1, 2)])
    assert total == ind.Frequencia(10, 6, 1, 3) and total.percentual == D("70.0")


# --- Desempenho (RN008, RN009, RN010) ------------------------------------------------


def _resultados(*ciclos):
    """Cada ciclo: dict área -> nota (None = faltou)."""
    lista = []
    for numero, areas in enumerate(ciclos, 1):
        for area in ind.AREAS:
            nota = areas.get(area, areas.get("*"))
            lista.append(
                ind.Resultado(
                    numero, SEG + timedelta(days=14 * numero), area, nota is not None, nota
                )
            )
    return lista


@pytest.mark.regras
def test_rn010_nota_total_e_rn009_area_ausente():
    assert ind.nota_total({a: D(600) for a in ind.AREAS}) == D("600.0")
    assert ind.nota_total(
        {"LINGUAGENS": D(601), "HUMANAS": D(600), "NATUREZA": D(600), "MATEMATICA": D(600)}
    ) == D("600.3")
    assert (
        ind.nota_total(
            {"LINGUAGENS": None, "HUMANAS": D(600), "NATUREZA": D(600), "MATEMATICA": D(600)}
        )
        is None
    )
    assert ind.nota_total({}) is None


@pytest.mark.regras
def test_rn008_delta_contra_o_proprio_historico_e_primeiro_simulado():
    historico = ind.notas_por_ciclo(_resultados({"*": D(650)}, {"*": D(590)}))
    valores = ind.serie(historico)
    assert ind.delta(valores, 1) is None  # primeiro simulado: sem base
    d = ind.delta(valores, 2)
    assert (d.atual, d.anterior, d.ciclo_anterior, d.valor) == (D(590), D(650), 1, D(-60))
    assert ind.delta(valores, 99) is None


@pytest.mark.regras
def test_rn009_ausente_nao_e_avaliado_e_a_base_pula_a_ausencia():
    historico = ind.notas_por_ciclo(_resultados({"*": D(650)}, {"*": None}, {"*": D(600)}))
    valores = ind.serie(historico)
    assert ind.delta(valores, 2) is None  # faltou: não avaliado no ciclo
    assert ind.delta(valores, 3).valor == D(-50) and ind.delta(valores, 3).ciclo_anterior == 1
    assert set(ind.deltas(valores)) == {1, 2, 3}


@pytest.mark.regras
def test_rn009_por_area():
    historico = ind.notas_por_ciclo(_resultados({"*": D(600)}, {"*": D(560), "LINGUAGENS": None}))
    assert ind.delta(ind.serie(historico, "LINGUAGENS"), 2) is None
    assert ind.delta(ind.serie(historico, "MATEMATICA"), 2).valor == D(-40)
    assert ind.delta(ind.serie(historico), 2) is None  # total exige as quatro áreas


@pytest.mark.regras
@pytest.mark.parametrize(
    "variacao,esperado",
    [
        (D(-31), ind.QUEDA),
        (D(-30), ind.QUEDA),
        (D("-29.9"), ind.ESTAGNADO),
        (D(0), ind.ESTAGNADO),
        (D("29.9"), ind.ESTAGNADO),
        (D(30), ind.EVOLUCAO),
        (D(31), ind.EVOLUCAO),
        (None, None),
    ],
)
def test_rn008_classificacao_nos_limites(variacao, esperado):
    assert ind.classificar(variacao, D(30)) == esperado


def test_media_ignora_nao_avaliados():
    assert ind.media([D(600), None, D(601)]) == D("600.5")
    assert ind.media([None]) is None


def test_participacao():
    p = ind.participacao([True, False, True, True])
    assert (p.registradas, p.entregues, p.percentual) == (4, 3, D("75.0"))
    assert ind.participacao([]).taxa is None and ind.participacao([]).percentual is None


# --- Integração com a base sintética -------------------------------------------------


@pytest.fixture
def base_2026(diretor):
    from ingestao.demonstracao import carregar

    carregar(2026, autor=diretor)


@pytest.mark.django_db
def test_consultas_com_a_base_sintetica(base_2026):
    from core.models import Aluno, CicloCalendario
    from inteligencia import consultas

    alunos = list(consultas.alunos_do_ano(2026))
    assert len(alunos) == 20
    semana = consultas.frequencias(alunos, date(2026, 4, 6), date(2026, 4, 10))
    assert semana["S260001"].faltas == 3  # perfil: três faltas na semana
    assert semana["S260002"].faltas == 2 and semana["S260002"].justificadas == 1  # RN002
    chamada = Aluno.objects.get(pk="S260005")
    antes = consultas.frequencias(
        [chamada], date(2026, 2, 2), chamada.data_ingresso - timedelta(days=1)
    )
    assert antes["S260005"].dias == 0  # RN004
    historicos = consultas.historicos(alunos)
    ciclos = list(CicloCalendario.objects.filter(data_inicio__year=2026).order_by("data_inicio"))
    queda = ind.serie(historicos["S260006"])
    assert ind.delta(queda, ciclos[7].pk).valor == D(-60)
    ausente = ind.serie(historicos["S260003"])
    assert ind.delta(ausente, ciclos[5].pk) is None  # RN009
    turmas = consultas.turmas_na_data(alunos, date(2026, 3, 2))
    assert len(turmas) == len([a for a in alunos if a.data_ingresso <= date(2026, 3, 2)])
    redacao = consultas.participacoes(alunos, date(2026, 2, 3), date(2026, 2, 3))
    assert redacao and all(p.registradas == 1 for p in redacao.values())


@pytest.mark.django_db
def test_comando_de_carga_so_em_desenvolvimento(settings, diretor, membro):
    from django.core.management import CommandError, call_command

    from core.models import ResultadoSimulado

    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG"):
        call_command("carregar_base_sintetica", autor="diretor")
    settings.DEBUG = True
    with pytest.raises(CommandError, match="Diretor"):
        call_command("carregar_base_sintetica", autor="membro")
    call_command("carregar_base_sintetica", autor="diretor", ano=2026)
    assert ResultadoSimulado.objects.count() > 0
