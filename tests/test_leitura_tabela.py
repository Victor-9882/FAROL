"""Leitura de CSV e XLSX (RF006; base de RF003 a RF005)."""

import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook

from ingestao import leitura
from ingestao.leitura import ArquivoInvalidoError, ler_tabela

COLUNAS = {
    "matricula": (),
    "nome": ("nome_completo",),
}


def _csv(texto, codificacao="utf-8"):
    return io.BytesIO(texto.encode(codificacao))


def _xlsx(linhas):
    livro = Workbook()
    aba = livro.active
    for linha in linhas:
        aba.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    saida.seek(0)
    return saida


@pytest.mark.parametrize("sep", [";", ","])
def test_csv_ponto_e_virgula_e_virgula(sep):
    linhas = ler_tabela(_csv(f"matricula{sep}nome\nS1{sep}Ana\n"), "a.csv")
    assert linhas == [{"matricula": "S1", "nome": "Ana", "_linha": 2}]


def test_csv_com_bom():
    linhas = ler_tabela(_csv("﻿matricula;nome\nS1;Ana\n"), "a.csv")
    assert linhas[0]["matricula"] == "S1"


def test_cabecalho_com_acento_e_espaco():
    linhas = ler_tabela(_csv("Matrícula;Data de Ingresso\nS1;02/02/2026\n"), "a.csv")
    assert set(linhas[0]) == {"matricula", "data_de_ingresso", "_linha"}


def test_sinonimo_vira_nome_canonico():
    linhas = ler_tabela(_csv("matrícula;Nome Completo\nS1;Ana\n"), "a.csv", colunas=COLUNAS)
    assert linhas[0]["nome"] == "Ana"


def test_linhas_vazias_sao_puladas_e_linha_conta_o_arquivo():
    linhas = ler_tabela(_csv("matricula;nome\n;\nS1;Ana\n"), "a.csv")
    assert [x["_linha"] for x in linhas] == [3]


def test_xlsx_gerado_em_memoria():
    arq = _xlsx([["Matrícula", "Nome", "Ingresso"], [260001, "Ana", datetime(2026, 2, 2)]])
    linhas = ler_tabela(arq, "a.xlsx")
    assert linhas[0]["matricula"] == "260001"
    assert linhas[0]["ingresso"] == date(2026, 2, 2)


def test_xlsx_corrompido_gera_erro():
    with pytest.raises(ArquivoInvalidoError):
        ler_tabela(io.BytesIO(b"nao e zip"), "a.xlsx")


def test_coluna_obrigatoria_ausente_gera_erro():
    with pytest.raises(ArquivoInvalidoError, match="nome"):
        ler_tabela(_csv("matricula;turma\nS1;A\n"), "a.csv", colunas=COLUNAS)


def test_extensao_desconhecida_gera_erro():
    with pytest.raises(ArquivoInvalidoError):
        ler_tabela(_csv("a;b\n1;2\n"), "a.txt")


@pytest.mark.parametrize("texto", ["matricula;nome\n", "matricula;nome\n;\n", ""])
def test_arquivo_sem_linhas_gera_erro(texto):
    with pytest.raises(ArquivoInvalidoError):
        ler_tabela(_csv(texto), "a.csv")


def test_limite_de_tamanho(monkeypatch):
    conteudo = "matricula;nome\nS1;Ana\n"
    monkeypatch.setattr(leitura, "TAMANHO_MAXIMO", len(conteudo.encode()))
    assert ler_tabela(_csv(conteudo), "a.csv")
    with pytest.raises(ArquivoInvalidoError):
        ler_tabela(_csv(conteudo + "x"), "a.csv")


def test_limite_de_linhas(settings):
    settings.IMPORTACAO_LIMITE_LINHAS = 2
    assert len(ler_tabela(_csv("m;n\n1;a\n2;b\n"), "a.csv")) == 2
    with pytest.raises(ArquivoInvalidoError):
        ler_tabela(_csv("m;n\n1;a\n2;b\n3;c\n"), "a.csv")


def test_cabecalho_fora_da_primeira_linha_e_linha_real_do_arquivo():
    arq = _xlsx([
        ["Controle de presença", None, None],
        [None, None, None],
        ["RM", "Nome Completo", "Turma"],
        [260001, "Ana", "T1"],
    ])  # fmt: skip
    colunas = {"matricula": ("rm",), "nome": ("nome_completo",), "turma": ()}
    linhas = ler_tabela(arq, "a.xlsx", colunas=colunas)
    assert linhas == [{"matricula": "260001", "nome": "Ana", "turma": "T1", "_linha": 4}]


def test_cabecalho_ausente_nas_primeiras_linhas_continua_erro():
    arq = _xlsx([["titulo", None], ["x", "y"], ["a", "b"]])
    with pytest.raises(ArquivoInvalidoError, match="matricula"):
        ler_tabela(arq, "a.xlsx", colunas=COLUNAS)


def _xlsx_inflado(linha, coluna):
    livro = Workbook()
    livro.active.cell(row=1, column=1, value="matricula")
    livro.active.cell(row=1, column=2, value="nome")
    livro.active.cell(row=2, column=1, value="S260001")
    livro.active.cell(row=2, column=2, value="Ana")
    livro.active.cell(row=linha, column=coluna, value="x")
    saida = io.BytesIO()
    livro.save(saida)
    saida.seek(0)
    return saida


def test_xlsx_inflado_em_linhas_e_recusado_sem_ler_a_aba_toda():
    import tracemalloc

    arq = _xlsx_inflado(200_000, 2)
    tracemalloc.start()
    with pytest.raises(ArquivoInvalidoError, match="limite"):
        ler_tabela(arq, "a.xlsx")
    pico = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert pico < 30 * 1024 * 1024


def test_xlsx_inflado_em_colunas_nao_consome_memoria():
    import tracemalloc

    arq = _xlsx_inflado(5_000, 16_384)
    tracemalloc.start()
    try:
        ler_tabela(arq, "a.xlsx")
    except ArquivoInvalidoError:
        pass
    pico = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert pico < 30 * 1024 * 1024


def test_csv_acima_do_limite_e_recusado(settings):
    settings.IMPORTACAO_LIMITE_LINHAS = 2
    with pytest.raises(ArquivoInvalidoError, match="limite"):
        ler_tabela(_csv("m;n\n" + "1;a\n" * 50), "a.csv")


def test_limite_linhas_por_parametro():
    texto = "m;n\n1;a\n2;b\n3;c\n"
    assert len(ler_tabela(_csv(texto), "a.csv", limite_linhas=3)) == 3
    with pytest.raises(ArquivoInvalidoError):
        ler_tabela(_csv(texto + "4;d\n"), "a.csv", limite_linhas=3)


def test_limite_linhas_zero_nao_vira_o_padrao():
    with pytest.raises(ArquivoInvalidoError, match="limite de 0"):
        ler_tabela(_csv("m;n\n1;a\n"), "a.csv", limite_linhas=0)
