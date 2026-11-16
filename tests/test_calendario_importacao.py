"""Importação do calendário, dos ciclos e dos temas (RF007, RN005 a RN007, NF007, NF008)."""

import io
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from core.models import CicloCalendario, DiaCalendario, RegistroAlteracao, TemaRedacao
from ingestao.calendario import TIPOS
from ingestao.leitura import ler_tabela

pytestmark = pytest.mark.django_db

PASTA = Path(__file__).parent / "dados_sinteticos" / "pequena" / "2026"
ARQUIVOS = {
    "dias": "calendario_letivo.csv",
    "ciclos": "ciclos.csv",
    "temas": "temas_redacao.csv",
}


def _arquivo(tipo):
    t = TIPOS[tipo]
    with open(PASTA / ARQUIVOS[tipo], "rb") as f:
        return ler_tabela(f, ARQUIVOS[tipo], colunas=t.colunas, opcionais=t.opcionais)


def _rodar(tipo, linhas, diretor, gravar=True, ano=2026):
    return TIPOS[tipo].importar(linhas, ano=ano, autor=diretor, gravar=gravar)


def _dia(data, letivo="S", descricao="", n=2):
    return {"data": data, "dia_letivo": letivo, "descricao": descricao, "_linha": n}


def test_importa_base_pequena_2026(diretor):
    r = _rodar("dias", _arquivo("dias"), diretor)
    assert (r.criados, r.inconsistentes) == (215, [])
    assert DiaCalendario.objects.filter(letivo=True).count() == 193
    assert DiaCalendario.objects.filter(letivo=False).count() == 22
    r = _rodar("ciclos", _arquivo("ciclos"), diretor)
    assert (r.criados, r.inconsistentes, r.avisos) == (20, [], [])
    r = _rodar("temas", _arquivo("temas"), diretor)
    assert (r.criados, r.inconsistentes) == (41, [])


@pytest.mark.parametrize("tipo", ["dias", "ciclos", "temas"])
def test_reimportar_nao_duplica(tipo, diretor):
    primeiro = _rodar(tipo, _arquivo(tipo), diretor)
    r = _rodar(tipo, _arquivo(tipo), diretor)
    assert (r.criados, r.atualizados) == (0, 0)
    assert r.sem_alteracao == primeiro.criados
    assert TIPOS[tipo].modelo.objects.count() == primeiro.criados


def test_conferir_nao_grava(diretor):
    r = _rodar("dias", _arquivo("dias"), diretor, gravar=False)
    assert r.criados == 215
    assert DiaCalendario.objects.count() == 0


def test_reimportar_com_mudanca_atualiza_e_audita(diretor):
    _rodar("dias", [_dia("16/02/2026", "S")], diretor)
    r = _rodar("dias", [_dia("16/02/2026", "N", "Carnaval")], diretor)
    assert (r.atualizados, r.criados) == (1, 0)
    dia = DiaCalendario.objects.get()
    assert dia.letivo is False and dia.descricao == "Carnaval"
    auditoria = RegistroAlteracao.objects.filter(modelo="core.diacalendario")
    assert set(auditoria.values_list("campo", flat=True)) == {"letivo", "descricao"}
    assert RegistroAlteracao.objects.get(campo="letivo").autor == diretor


def test_data_repetida_no_arquivo(diretor):
    r = _rodar("dias", [_dia("16/02/2026", n=2), _dia("16/02/2026", "N", n=3)], diretor)
    assert r.criados == 1
    assert [n for n, _ in r.inconsistentes] == [3]


def test_data_de_outro_ano_e_inconsistente(diretor):
    r = _rodar("dias", [_dia("31/12/2026", n=2), _dia("01/01/2027", n=3)], diretor)
    assert r.criados == 1
    assert [n for n, _ in r.inconsistentes] == [3]


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("S", True), ("N", False), ("sim", True), ("não", False), ("1", True), (0, False),
     (True, True), (False, False), ("X", None)],
)  # fmt: skip
def test_dia_letivo_valores_aceitos(valor, esperado, diretor):
    r = _rodar("dias", [_dia("16/02/2026", valor)], diretor)
    if esperado is None:
        assert len(r.inconsistentes) == 1 and r.criados == 0
    else:
        assert DiaCalendario.objects.get().letivo is esperado


@pytest.mark.parametrize("valor", ["31/02/2026", "abc", ""])
def test_data_invalida(valor, diretor):
    r = _rodar("dias", [_dia(valor)], diretor)
    assert len(r.inconsistentes) == 1 and r.criados == 0


def test_xlsx_em_memoria(diretor):
    livro = Workbook()
    aba = livro.active
    aba.append(["data", "tema"])
    aba.append([date(2026, 2, 3), "Tema A"])
    aba.append([date(2026, 2, 10), "Tema B"])
    saida = io.BytesIO()
    livro.save(saida)
    saida.seek(0)
    t = TIPOS["temas"]
    linhas = ler_tabela(saida, "t.xlsx", colunas=t.colunas, opcionais=t.opcionais)
    assert _rodar("temas", linhas, diretor).criados == 2


def test_limites_de_texto(diretor):
    t200, t201 = "t" * 200, "t" * 201
    r = _rodar(
        "temas",
        [
            {"data": "03/02/2026", "tema": t200, "_linha": 2},
            {"data": "10/02/2026", "tema": t201, "_linha": 3},
        ],
        diretor,
    )
    assert (r.criados, [n for n, _ in r.inconsistentes]) == (1, [3])
    r = _rodar(
        "dias",
        [_dia("16/02/2026", descricao="d" * 100), _dia("17/02/2026", descricao="d" * 101, n=3)],
        diretor,
    )
    assert (r.criados, [n for n, _ in r.inconsistentes]) == (1, [3])


def test_tema_fora_da_terca_e_inconsistente(diretor):
    r = _rodar("temas", [{"data": "02/02/2026", "tema": "x", "_linha": 2}], diretor)
    assert len(r.inconsistentes) == 1 and TemaRedacao.objects.count() == 0


def test_ausente_do_arquivo_nao_e_alterado(diretor):
    _rodar("dias", [_dia("16/02/2026"), _dia("17/02/2026", n=3)], diretor)
    _rodar("dias", [_dia("16/02/2026", "N")], diretor)
    assert DiaCalendario.objects.get(data=date(2026, 2, 17)).letivo is True
    assert DiaCalendario.objects.count() == 2


def _ciclo(ini, fim, sim="", n=2):
    return {"data_inicio": ini, "data_fim": fim, "data_simulado": sim, "_linha": n}


def test_ciclo_duracao_diferente_de_14_dias_avisa_e_importa(diretor):
    linhas = [
        _ciclo("02/02/2026", "15/02/2026", n=2),  # 14 dias
        _ciclo("16/02/2026", "27/02/2026", n=3),  # 12 dias
    ]
    r = _rodar("ciclos", linhas, diretor)
    assert r.criados == 2 and [n for n, _ in r.avisos] == [3]


def test_ciclo_sobreposto_e_simulado_fora_sao_inconsistentes(diretor):
    linhas = [
        _ciclo("02/02/2026", "15/02/2026", "15/02/2026", n=2),
        _ciclo("15/02/2026", "28/02/2026", n=3),
        _ciclo("01/03/2026", "14/03/2026", "15/03/2026", n=4),
    ]
    r = _rodar("ciclos", linhas, diretor)
    assert r.criados == 1 and [n for n, _ in r.inconsistentes] == [3, 4]


def test_ciclo_atualiza_data_simulado(diretor):
    _rodar("ciclos", [_ciclo("02/02/2026", "15/02/2026")], diretor)
    r = _rodar("ciclos", [_ciclo("02/02/2026", "15/02/2026", "15/02/2026")], diretor)
    assert r.atualizados == 1
    assert CicloCalendario.objects.get().data_simulado == date(2026, 2, 15)
