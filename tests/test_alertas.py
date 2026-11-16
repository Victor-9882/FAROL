"""Regras e geração de alertas (#24, #25, #26; RF014, RF015, RN001, RN002, RN005, RN008,
RN009, RN012, NF004, NF005, NF021). Só dados sintéticos (NF017)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from core.models import (
    Alerta,
    Aluno,
    CicloCalendario,
    DiaCalendario,
    PeriodoLetivo,
    RegistroFrequencia,
    ResultadoSimulado,
    Turma,
)
from inteligencia import alertas, regras
from inteligencia.models import RegraAlerta

pytestmark = pytest.mark.django_db

SEG = date(2026, 3, 2)
D = Decimal


@pytest.fixture
def aluno(db):
    PeriodoLetivo.objects.create(inicio=date(2026, 2, 2), fim=date(2026, 11, 27))
    turma = Turma.objects.create(nome="Turma 1", ano=2026)
    return Aluno.objects.create(
        matricula="S260001", nome="Aluno Um", data_ingresso=date(2026, 2, 2), turma=turma
    )


def _semana(aluno, codigos, segunda=SEG):
    for n, c in enumerate(codigos):
        RegistroFrequencia.objects.update_or_create(
            aluno=aluno,
            data=segunda + timedelta(days=n),
            defaults={"presente": c == "P", "justificada": c == "J"},
        )


def _ciclos(n):
    return [
        CicloCalendario.objects.create(
            data_inicio=SEG + timedelta(days=14 * i),
            data_fim=SEG + timedelta(days=14 * i + 13),
            data_simulado=SEG + timedelta(days=14 * i + 13),
        )
        for i in range(n)
    ]


def _notas(aluno, ciclo, nota=None, **por_area):
    for area in ("LINGUAGENS", "HUMANAS", "NATUREZA", "MATEMATICA"):
        valor = por_area.get(area, nota)
        ResultadoSimulado.objects.create(
            aluno=aluno,
            ciclo=ciclo,
            area=area,
            presente=valor is not None,
            nota_tri=None if valor is None else D(str(valor)),
            acertos=None if valor is None else 30,
        )


# --- Regras padrão (IC-10, RF018) ----------------------------------------------------


def test_regras_padrao_carregadas_pela_migracao():
    vigentes = {r.tipo_regra: r for r in RegraAlerta.objects.filter(ativa=True)}
    assert vigentes["FREQUENCIA"].limiar == 3 and vigentes["DESEMPENHO"].limiar == 30
    assert "pelo menos 3 faltas" in vigentes["FREQUENCIA"].descricao
    assert "{limiar}" not in vigentes["DESEMPENHO"].descricao
    assert regras.criar_padroes(RegraAlerta) == 0  # já existem: nada muda


def test_padroes_do_arquivo(tmp_path):
    arquivo = tmp_path / "regras.yaml"
    arquivo.write_text("FREQUENCIA:\n  limiar: 2.5\n  descricao: 'mais de {limiar}'\n")
    assert regras.padroes(arquivo) == {
        "FREQUENCIA": {"limiar": D("2.5"), "descricao": "mais de 2.5"}
    }


# --- RF014: frequência semanal (RN001, RN002, RN005, NF005) ----------------------------


@pytest.mark.regras
@pytest.mark.parametrize("codigos,alerta", [("PPFFP", False), ("PFFFP", True), ("FFFFF", True)])
def test_rf014_limiar_de_tres_faltas_nos_dois_lados(aluno, codigos, alerta):
    _semana(aluno, codigos)
    alertas.gerar_frequencia(SEG, 2026)
    assert Alerta.objects.filter(tipo="FREQUENCIA", ativo=True).exists() is alerta


@pytest.mark.regras
def test_rf014_justificada_e_dia_nao_letivo_nao_contam(aluno):
    _semana(aluno, "FFJJP")
    alertas.gerar_frequencia(SEG, 2026)
    assert not Alerta.objects.exists()  # RN002: só 2 não justificadas
    _semana(aluno, "FFFPP")
    DiaCalendario.objects.create(data=SEG, letivo=False, descricao="Emenda")
    alertas.gerar_frequencia(SEG, 2026)
    assert not Alerta.objects.exists()  # RN005: a segunda deixou de ser letiva


@pytest.mark.regras
def test_rf014_motivo_regra_e_nf005_um_por_semana(aluno):
    _semana(aluno, "FFFPP")
    g = alertas.gerar_frequencia(SEG + timedelta(days=3), 2026)  # qualquer dia da semana
    assert g.novos == 1
    alerta = Alerta.objects.get()
    assert alerta.semana == SEG and alerta.regra.tipo_regra == "FREQUENCIA"
    assert alerta.motivo.startswith("3 falta(s) não justificada(s) na semana de 02/03 a 08/03/2026")
    assert "limiar: 3 faltas" in alerta.motivo
    assert alertas.gerar_frequencia(SEG, 2026).mantidos == 1 and Alerta.objects.count() == 1
    _semana(aluno, "FFFFP")
    assert alertas.gerar_frequencia(SEG, 2026).atualizados == 1
    assert Alerta.objects.get().motivo.startswith("4 falta(s)")
    with pytest.raises(IntegrityError), transaction.atomic():
        Alerta.objects.create(
            aluno=aluno, tipo="FREQUENCIA", semana=SEG, motivo="x", data_geracao=alerta.data_geracao
        )


def test_rf014_dado_corrigido_desativa_e_reativa(aluno):
    _semana(aluno, "FFFPP")
    alertas.gerar_frequencia(SEG, 2026)
    _semana(aluno, "PPPPP")
    assert alertas.gerar_frequencia(SEG, 2026).desativados == 1
    assert Alerta.objects.get().ativo is False  # NF007: não some
    _semana(aluno, "FFFPP")
    assert alertas.gerar_frequencia(SEG, 2026).atualizados == 1 and Alerta.objects.get().ativo


def test_sem_regra_ativa_nao_gera(aluno):
    RegraAlerta.objects.update(ativa=False)
    _semana(aluno, "FFFFF")
    assert alertas.gerar_frequencia(SEG, 2026).sem_regra
    assert alertas.gerar_desempenho(_ciclos(1)[0]).sem_regra
    assert not Alerta.objects.exists()


# --- RF015: desempenho por ciclo (RN008, RN009) --------------------------------------


@pytest.mark.regras
@pytest.mark.parametrize("nova,alerta", [(569, True), (570, True), (571, False)])
def test_rf015_limiar_de_30_pontos(aluno, nova, alerta):
    um, dois = _ciclos(2)
    _notas(aluno, um, 600)
    _notas(aluno, dois, nova)  # delta -31, -30 e -29
    alertas.gerar_desempenho(dois)
    assert Alerta.objects.filter(tipo="DESEMPENHO", ciclo=dois).exists() is alerta


@pytest.mark.regras
def test_rf015_primeiro_simulado_e_ausente_nao_sao_avaliados(aluno):
    um, dois, tres = _ciclos(3)
    _notas(aluno, um, 650)
    _notas(aluno, dois, None)  # faltou (RN009)
    _notas(aluno, tres, 600)
    assert alertas.gerar_desempenho(um).novos == 0  # sem base de comparação
    assert alertas.gerar_desempenho(dois).novos == 0
    alertas.gerar_desempenho(tres)
    alerta = Alerta.objects.get()  # a base é o ciclo 1: 650 -> 600
    assert alerta.area == "" and "650 → 600 (-50)" in alerta.motivo


@pytest.mark.regras
def test_rf015_queda_so_numa_area(aluno):
    um, dois = _ciclos(2)
    _notas(aluno, um, 600)
    _notas(aluno, dois, 600, MATEMATICA=560, LINGUAGENS=None)
    alertas.gerar_desempenho(dois)
    alerta = Alerta.objects.get()
    assert alerta.area == "MATEMATICA" and "Matemática: 600 → 560 (-40)" in alerta.motivo
    assert "Linguagens" not in alerta.motivo  # RN009: faltou à área, não é avaliada


def test_rf015_regerar_o_ano_e_idempotente(aluno):
    um, dois = _ciclos(2)
    _notas(aluno, um, 650)
    _notas(aluno, dois, 590)
    assert alertas.gerar_desempenho_ano(2026).novos == 1
    assert alertas.gerar_desempenho_ano(2026).mantidos == 1 and Alerta.objects.count() == 1


# --- Base sintética, comando e importação --------------------------------------------


def test_perfis_da_base_sintetica(diretor):
    from ingestao.demonstracao import carregar

    contagens = carregar(2026, autor=diretor)
    assert contagens["alertas"] == Alerta.objects.count() > 0
    tres = Alerta.objects.filter(aluno_id="S260001", tipo="FREQUENCIA")
    assert tres.filter(semana=date(2026, 4, 6)).exists()  # três faltas na semana
    assert not Alerta.objects.filter(aluno_id="S260002", semana=date(2026, 4, 6)).exists()  # RN002
    ciclos = list(CicloCalendario.objects.filter(data_inicio__year=2026).order_by("data_inicio"))
    assert Alerta.objects.filter(aluno_id="S260006", tipo="DESEMPENHO", ciclo=ciclos[7]).exists()
    assert not Alerta.objects.filter(aluno_id="S260003", ciclo=ciclos[5]).exists()  # RN009
    assert not Alerta.objects.filter(aluno_id="S260007", tipo="DESEMPENHO").exists()  # só sobe
    assert all(a.motivo and a.regra_id for a in Alerta.objects.all())  # NF004, RF018


def test_comando_gerar_alertas(aluno, capsys):
    _semana(aluno, "FFFPP")
    call_command("gerar_alertas", ano=2026)
    saida = capsys.readouterr().out
    assert "frequência: 1 novo(s)" in saida and "desempenho: 0 novo(s)" in saida
    RegraAlerta.objects.update(ativa=False)
    call_command("gerar_alertas", ano=2026)
    assert "sem regra ativa" in capsys.readouterr().out
    call_command("gerar_alertas", ano=2030)


def test_importar_a_grade_gera_os_alertas(cliente_diretor, aluno):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.urls import reverse

    from ingestao import planilhas_casd
    from tests.conftest import importar_em_dois_passos

    codigos = {("S260001", SEG + timedelta(days=n)): c for n, c in enumerate("FFFPP")}
    conteudo = planilhas_casd.grade_presenca(
        2026, [{"nome": "Aluno Um", "matricula": "S260001", "turma": "T"}], codigos
    )

    def montar(acao):
        return {
            "arquivo": SimpleUploadedFile("g.xlsx", conteudo),
            "ano": 2026,
            "aba": "",
            "acao": acao,
        }

    cliente_diretor.post(reverse("web:frequencia_importar"), montar("conferir"))
    assert not Alerta.objects.exists()  # conferir não grava nem gera
    importar_em_dois_passos(cliente_diretor, reverse("web:frequencia_importar"), montar)
    assert Alerta.objects.filter(tipo="FREQUENCIA", semana=SEG).count() == 1


def test_importar_simulado_gera_os_alertas(cliente_diretor, aluno):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.urls import reverse

    from ingestao import planilhas_casd
    from tests.conftest import importar_em_dois_passos

    um, dois = _ciclos(2)
    _notas(aluno, um, 650)
    areas = ("HUMANAS", "LINGUAGENS", "NATUREZA", "MATEMATICA")
    linha = {
        "matricula": "S260001",
        "nome": "Aluno Um",
        "id_aluno": 1,
        "inscricao": "1",
        "turma": "T",
        "notas": {a: 590.0 for a in areas},
        "acertos": {a: 20 for a in areas},
    }
    conteudo = planilhas_casd.relatorio_pmais("Simulado", 2026, [linha])

    def montar(acao):
        return {
            "arquivo": SimpleUploadedFile("p.xlsm", conteudo),
            "ano": 2026,
            "ciclo": dois.pk,
            "acao": acao,
        }

    importar_em_dois_passos(cliente_diretor, reverse("web:simulados_importar"), montar)
    assert Alerta.objects.get(tipo="DESEMPENHO").ciclo == dois


def test_associar_pendencia_regera_alertas(cliente_diretor, diretor, aluno):
    from django.urls import reverse

    from core.models import PendenciaImportacao
    from ingestao.pendencias import registrar_pendencia

    _semana(aluno, "PPPPP")
    codigos = {(SEG + timedelta(days=n)).isoformat(): c for n, c in enumerate("FFFPP")}
    registrar_pendencia(
        origem="FREQUENCIA",
        motivo="EM_BRANCO",
        ano=2026,
        data=SEG,
        matricula="",
        nome="Aluno Um",
        referencia="grade",
        dados={"codigos": codigos},
    )
    pendencia = PendenciaImportacao.objects.get()
    cliente_diretor.post(
        reverse("web:pendencias"),
        {"acao": "associar", "pendencia": [pendencia.pk], "matricula": "S260001"},
    )
    assert Alerta.objects.filter(tipo="FREQUENCIA", semana=SEG, ativo=True).exists()
