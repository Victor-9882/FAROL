"""Testes do gerador de base sintética (#7; NF017, NF012)."""

import csv
import importlib.util
import json
import sys
from collections import Counter
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
BASE_PEQUENA = RAIZ / "tests" / "dados_sinteticos" / "pequena"

_spec = importlib.util.spec_from_file_location(
    "gerar_base_sintetica", RAIZ / "scripts" / "gerar_base_sintetica.py"
)
gerador = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gerador  # exigido por @dataclass
_spec.loader.exec_module(gerador)


def ler(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def data(texto: str) -> date:
    return datetime.strptime(texto, "%d/%m/%Y").date()


def conteudo(pasta: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(pasta)): p.read_bytes() for p in sorted(pasta.rglob("*")) if p.is_file()
    }


@pytest.fixture(scope="module")
def perfis():
    resumo = json.loads((BASE_PEQUENA / "perfis_conhecidos.json").read_text(encoding="utf-8"))
    return {p["perfil"]: p for p in resumo["perfis"]}, resumo


def ano_dir():
    return BASE_PEQUENA / "2026"


# --- Reprodutibilidade --------------------------------------------------------------


def test_mesma_semente_gera_os_mesmos_arquivos(tmp_path):
    gerador.gerar(tmp_path / "a", gerador.TAMANHOS["pequena"], semente=28)
    gerador.gerar(tmp_path / "b", gerador.TAMANHOS["pequena"], semente=28)
    assert conteudo(tmp_path / "a") == conteudo(tmp_path / "b")


def test_semente_diferente_gera_outra_base(tmp_path):
    gerador.gerar(tmp_path / "a", gerador.TAMANHOS["pequena"], semente=28)
    gerador.gerar(tmp_path / "b", gerador.TAMANHOS["pequena"], semente=29)
    assert conteudo(tmp_path / "a") != conteudo(tmp_path / "b")


def test_base_versionada_corresponde_ao_gerador(tmp_path):
    """Quem muda o gerador precisa regerar e versionar a base pequena."""
    gerador.main(["--destino", str(tmp_path)])
    versionada = {k: v for k, v in conteudo(BASE_PEQUENA).items() if k.endswith((".csv", ".json"))}
    assert conteudo(tmp_path) == versionada


# --- Tamanho (NF012) ----------------------------------------------------------------


def test_base_completa_tem_500_alunos_em_5_turmas_por_ano(tmp_path):
    resumo = gerador.gerar(tmp_path, gerador.TAMANHOS["completa"])
    assert list(resumo["anos"]) == ["2024", "2025", "2026"]
    for ano, info in resumo["anos"].items():
        cadastro = ler(tmp_path / ano / "cadastro_alunos.csv")
        assert len(cadastro) == info["alunos"] == 500
        assert len({linha["turma"] for linha in cadastro}) == 5


def test_matriculas_unicas_e_sinteticas():
    matriculas = []
    for ano in ("2024", "2025", "2026"):
        matriculas += [a["matricula"] for a in ler(BASE_PEQUENA / ano / "cadastro_alunos.csv")]
    assert len(matriculas) == len(set(matriculas)) == 60
    assert all(m.startswith("S") for m in matriculas)


# --- Calendário (RN005, RN006, RN007) -----------------------------------------------


def test_feriados_e_recesso_nao_sao_dias_letivos():
    calendario = {data(d["data"]): d for d in ler(ano_dir() / "calendario_letivo.csv")}
    assert calendario[date(2026, 4, 21)]["dia_letivo"] == "N"  # Tiradentes
    assert calendario[date(2026, 2, 16)]["descricao"] == "Carnaval"
    assert calendario[date(2026, 7, 8)]["descricao"] == "Recesso escolar"
    assert all(d.weekday() < 5 for d in calendario)


def test_catraca_so_tem_passagens_em_dias_letivos():
    letivos = {
        d["data"] for d in ler(ano_dir() / "calendario_letivo.csv") if d["dia_letivo"] == "S"
    }
    assert {p["data"] for p in ler(ano_dir() / "catraca_presencas.csv")} <= letivos


def test_simulados_a_cada_duas_semanas():
    ciclos = ler(ano_dir() / "ciclos.csv")
    for ciclo in ciclos:
        inicio, fim = data(ciclo["data_inicio"]), data(ciclo["data_fim"])
        assert (fim - inicio).days == 13
        assert ciclo["data_simulado"] == ciclo["data_fim"]
    # Ciclos consecutivos, exceto o salto do recesso de julho.
    saltos = Counter(
        (data(b["data_inicio"]) - data(a["data_inicio"])).days for a, b in pairwise(ciclos)
    )
    assert saltos[14] == len(ciclos) - 2
    assert saltos[28] == 1


def test_tema_de_redacao_toda_terca():
    assert all(data(t["data"]).weekday() == 1 for t in ler(ano_dir() / "temas_redacao.csv"))


# --- Perfis com resultado conhecido -------------------------------------------------


def ausencias(matricula: str) -> list[date]:
    letivos = [
        data(d["data"]) for d in ler(ano_dir() / "calendario_letivo.csv") if d["dia_letivo"] == "S"
    ]
    presentes = {
        data(p["data"])
        for p in ler(ano_dir() / "catraca_presencas.csv")
        if p["matricula"] == matricula
    }
    return [d for d in letivos if d not in presentes]


def justificadas(matricula: str) -> set[date]:
    return {
        data(j["data"])
        for j in ler(ano_dir() / "justificativas.csv")
        if j["matricula"] == matricula
    }


def test_perfil_tres_faltas_na_semana(perfis):
    perfil = perfis[0]["tres_faltas_na_semana"]
    esperado = [data(d) for d in perfil["esperado"]["datas"]]
    assert ausencias(perfil["matricula"]) == esperado
    assert {d.isocalendar().week for d in esperado} == {esperado[0].isocalendar().week}
    assert not justificadas(perfil["matricula"])


def test_perfil_falta_justificada(perfis):
    perfil = perfis[0]["falta_justificada"]
    faltas = ausencias(perfil["matricula"])
    assert len(faltas) == perfil["esperado"]["ausencias"] == 3
    assert justificadas(perfil["matricula"]) == {data(perfil["esperado"]["data_justificada"])}
    nao_justificadas = [d for d in faltas if d not in justificadas(perfil["matricula"])]
    assert len(nao_justificadas) == perfil["esperado"]["faltas_nao_justificadas"] == 2


def test_perfil_ausente_no_simulado(perfis):
    perfil = perfis[0]["ausente_no_simulado"]
    linhas = [
        s for s in ler(ano_dir() / "p_mais_simulados.csv") if s["matricula"] == perfil["matricula"]
    ]
    ausente = [s for s in linhas if s["presenca"] == "Ausente"]
    assert [s["data"] for s in ausente] == [perfil["esperado"]["data_simulado"]]
    assert all(ausente[0][f"{area}_tri"] == "" for area in gerador.AREAS)
    assert all(s["MT_tri"] == "600,0" for s in linhas if s["presenca"] == "Presente")


def test_perfil_mudou_de_turma(perfis):
    perfil = perfis[0]["mudou_de_turma"]
    esperado = perfil["esperado"]
    historico = [
        h for h in ler(ano_dir() / "historico_turmas.csv") if h["matricula"] == perfil["matricula"]
    ]
    assert [(h["turma"], h["data_fim"]) for h in historico] == [
        (esperado["turma_anterior"], esperado["data_mudanca"]),
        (esperado["turma_nova"], ""),
    ]
    cadastro = {a["matricula"]: a for a in ler(ano_dir() / "cadastro_alunos.csv")}
    assert cadastro[perfil["matricula"]]["turma"] == esperado["turma_nova"]
    # Registros dos dois lados da mudança (o histórico anterior existe).
    passagens = [
        data(p["data"])
        for p in ler(ano_dir() / "catraca_presencas.csv")
        if p["matricula"] == perfil["matricula"]
    ]
    mudanca = data(esperado["data_mudanca"])
    assert min(passagens) < mudanca <= max(passagens)


def test_perfil_segunda_chamada(perfis):
    perfil = perfis[0]["segunda_chamada"]
    ingresso = data(perfil["esperado"]["data_ingresso"])
    passagens = [
        data(p["data"])
        for p in ler(ano_dir() / "catraca_presencas.csv")
        if p["matricula"] == perfil["matricula"]
    ]
    assert min(passagens) == ingresso
    # As "ausências" anteriores ao ingresso não são faltas (RN004); depois dele, nenhuma.
    assert all(d < ingresso for d in ausencias(perfil["matricula"]))


def tri_por_ciclo(matricula: str) -> list[float]:
    linhas = [s for s in ler(ano_dir() / "p_mais_simulados.csv") if s["matricula"] == matricula]
    return [float(s["MT_tri"].replace(",", ".")) for s in linhas]


def test_perfil_queda_de_desempenho(perfis):
    perfil = perfis[0]["queda_de_desempenho"]
    notas = tri_por_ciclo(perfil["matricula"])
    ciclo = perfil["esperado"]["ciclo_queda"]
    assert notas[ciclo - 1] - notas[ciclo - 2] == perfil["esperado"]["delta_tri"] == -60.0
    assert len(set(notas[: ciclo - 1])) == 1


def test_perfil_evolucao_consistente(perfis):
    perfil = perfis[0]["evolucao_consistente"]
    notas = tri_por_ciclo(perfil["matricula"])
    assert notas[0] == perfil["esperado"]["nota_ciclo_1"]
    assert {b - a for a, b in pairwise(notas)} == {perfil["esperado"]["delta_tri_por_ciclo"]}


# --- Inconsistências conhecidas (NF006) ---------------------------------------------


def test_inconsistencias_conhecidas_estao_nos_arquivos(perfis):
    inconsistencias = {i["tipo"]: i for i in perfis[1]["inconsistencias"]}
    cadastro = {a["matricula"] for a in ler(ano_dir() / "cadastro_alunos.csv")}

    desconhecida = inconsistencias["matricula_desconhecida"]
    catraca = ler(BASE_PEQUENA / desconhecida["arquivo"])
    assert [p["matricula"] for p in catraca if p["matricula"] not in cadastro] == ["S999999"]

    em_branco = inconsistencias["matricula_em_branco"]
    redacoes = ler(BASE_PEQUENA / em_branco["arquivo"])
    assert [r["nome"] for r in redacoes if r["matricula"] == ""] == [em_branco["nome"]]
