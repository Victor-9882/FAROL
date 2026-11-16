"""Importação das redações do Corrija-me (RF005, RN003, RN004, RN007, NF006, NF008, NF009).

Só dados sintéticos (NF017): a base `pequena/2026` e linhas inventadas.
"""

import io
import json
from datetime import date
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import (
    Aluno,
    PendenciaImportacao,
    RegistroAlteracao,
    RegistroImportacao,
    ResultadoRedacao,
    TemaRedacao,
    Turma,
)
from ingestao import pendencias
from ingestao.cadastro import COLUNAS as COLUNAS_CADASTRO
from ingestao.cadastro import importar_cadastro
from ingestao.leitura import ler_data, ler_tabela
from ingestao.redacoes import COLUNAS, OPCIONAIS, aplicar_pendencia, importar_redacoes
from tests.conftest import importar_em_dois_passos

pytestmark = pytest.mark.django_db

PASTA = Path(__file__).parent / "dados_sinteticos" / "pequena"
CONHECIDOS = json.loads((PASTA / "perfis_conhecidos.json").read_text())
CABECALHO = "data_tema;tema;matricula;nome;entregue;c1;c2;c3;c4;c5;total\n"
TERCA = date(2026, 3, 3)
NOTAS = "160;160;160;160;160;800"
VAZIO = ";;;;;"


def _ler(nome, colunas, opcionais=frozenset()):
    with (PASTA / "2026" / nome).open("rb") as f:
        return ler_tabela(f, nome, colunas=colunas, opcionais=opcionais)


def _csv(corpo):
    texto = CABECALHO + corpo
    return ler_tabela(io.BytesIO(texto.encode()), "r.csv", colunas=COLUNAS, opcionais=OPCIONAIS)


def _linha(
    matricula="S260001",
    entregue="S",
    notas=NOTAS,
    data="03/03/2026",
    tema="Tema A",
    nome="Aluno Sintético Um",
):
    return f"{data};{tema};{matricula};{nome};{entregue};{notas}\n"


@pytest.fixture
def ano_2026(diretor):
    importar_cadastro(
        _ler("cadastro_alunos.csv", COLUNAS_CADASTRO, frozenset({"data_ingresso"})),
        ano=2026,
        autor=diretor,
        data_mudanca=date(2026, 6, 25),
        gravar=True,
    )


@pytest.fixture
def aluno(db):
    turma = Turma.objects.create(nome="Turma A", ano=2026)
    return Aluno.objects.create(
        matricula="S260001", nome="Aluno Sintético Um", data_ingresso=date(2026, 2, 2), turma=turma
    )


def _importar(corpo, autor, gravar=True):
    return importar_redacoes(_csv(corpo), ano=2026, autor=autor, gravar=gravar)


# --- Base sintética do ano todo ------------------------------------------------------


def test_ano_sintetico(diretor, ano_2026):
    linhas = _ler("corrija_me_redacoes.csv", COLUNAS, OPCIONAIS)
    resumo = importar_redacoes(linhas, ano=2026, autor=diretor, gravar=True)
    assert resumo.total_linhas == len(linhas) and not resumo.inconsistentes
    # RN007: os temas vêm do arquivo, um por terça
    temas = _ler("temas_redacao.csv", {"data": (), "tema": ()})
    assert resumo.temas_criados == len(temas) == TemaRedacao.objects.count()
    assert TemaRedacao.objects.get(data=TERCA).tema == next(
        t["tema"] for t in temas if ler_data(t["data"]) == TERCA
    )
    # não entregue fica registrada, sem nota
    assert resumo.nao_entregues == 191
    nao = ResultadoRedacao.objects.filter(entregue=False)
    assert nao.count() == 191 and not nao.exclude(nota_c1__isnull=True).exists()
    # RN003: a redação sem matrícula do export vira pendência
    em_branco = next(i for i in CONHECIDOS["inconsistencias"] if i["tipo"] == "matricula_em_branco")
    pendencia = PendenciaImportacao.objects.get()
    assert pendencia.motivo == "EM_BRANCO" and pendencia.nome_informado == em_branco["nome"]
    assert pendencia.data == date(2026, 2, 24)
    assert len(resumo.pendencias) == 1
    assert ResultadoRedacao.objects.count() == len(linhas) - 1


def test_reimportar_nao_duplica(diretor, ano_2026):
    linhas = _ler("corrija_me_redacoes.csv", COLUNAS, OPCIONAIS)
    importar_redacoes(linhas, ano=2026, autor=diretor, gravar=True)
    segunda = importar_redacoes(linhas, ano=2026, autor=diretor, gravar=True)
    assert segunda.importados == 0 and segunda.temas_criados == 0
    assert segunda.sem_alteracao == len(linhas) - 1 and len(segunda.pendencias) == 1
    assert ResultadoRedacao.objects.count() == len(linhas) - 1
    assert PendenciaImportacao.objects.count() == 1
    assert segunda.sobreposicoes


# --- Regras e valores-limite (RN007) -------------------------------------------------


def test_entregue_e_nao_entregue(diretor, aluno):
    Aluno.objects.create(
        matricula="S260002", nome="Dois", data_ingresso=date(2026, 2, 2), turma=aluno.turma
    )
    resumo = _importar(_linha() + _linha("S260002", "N", VAZIO), diretor)
    assert (resumo.criados, resumo.entregues, resumo.nao_entregues) == (2, 1, 1)
    um = ResultadoRedacao.objects.get(aluno=aluno)
    assert um.entregue and um.nota_total == 800 and um.tema == "Tema A" and um.tema_semana == TERCA
    dois = ResultadoRedacao.objects.get(aluno_id="S260002")
    assert not dois.entregue and dois.nota_total is None


@pytest.mark.parametrize(
    "entregue,notas,data,motivo",
    [
        ("N", NOTAS, "03/03/2026", "redação não entregue com nota"),
        ("S", ";160;160;160;160;", "03/03/2026", "competência 1 em branco em redação entregue"),
        ("S", "201;160;160;160;160;", "03/03/2026", "competência 1 fora de 0 a 200"),
        ("S", "160;-1;160;160;160;", "03/03/2026", "competência 2 fora de 0 a 200"),
        ("S", "160;160;160;160;160;801", "03/03/2026", "total diferente da soma das competências"),
        ("X", VAZIO, "03/03/2026", "entrega inválida (use S ou N)"),
        ("S", NOTAS, "04/03/2026", "a data do tema precisa ser uma terça-feira (RN007)"),
        ("S", NOTAS, "03/03/2025", "data do tema fora do ano letivo informado"),
        ("S", NOTAS, "", "data do tema em branco"),
        ("S", NOTAS, "xx", "data do tema inválida (use dd/mm/aaaa ou aaaa-mm-dd)"),
    ],
)
def test_linhas_invalidas(diretor, aluno, entregue, notas, data, motivo):
    resumo = _importar(_linha(entregue=entregue, notas=notas, data=data), diretor)
    assert [m for _, _, m in resumo.inconsistentes] == [motivo]
    assert not ResultadoRedacao.objects.exists()


def test_valores_limite_e_total_opcional(diretor, aluno):
    resumo = _importar(_linha(notas="0;200;0;200;0;"), diretor)
    assert resumo.criados == 1 and ResultadoRedacao.objects.get().nota_total == 400
    resumo = _importar(_linha("S260001", "N", ";;;;;0", data="10/03/2026"), diretor)
    assert resumo.criados == 1  # não entregue com total 0 é aceito


def test_tema_cadastrado_e_mantido_e_avisa(diretor, aluno):
    TemaRedacao.objects.create(data=TERCA, tema="Tema cadastrado")
    resumo = _importar(
        _linha(tema="Outro título") + _linha("S269999", tema="Outro título"), diretor
    )
    assert resumo.temas_criados == 0
    assert [m for _, m in resumo.avisos] == [
        "03/03/2026: o tema do arquivo difere do cadastrado; mantido o cadastrado"
    ]
    assert ResultadoRedacao.objects.get().tema == "Tema cadastrado"
    # mesmo título, só com caixa e acento diferentes: sem aviso
    resumo = _importar(_linha(tema="TEMA CADASTRADO"), diretor)
    assert not resumo.avisos


def test_tema_em_branco_sem_cadastro_e_inconsistente(diretor, aluno):
    resumo = _importar(_linha(tema=""), diretor)
    assert resumo.inconsistentes[0][2] == "tema em branco e não cadastrado para esta terça"
    TemaRedacao.objects.create(data=TERCA, tema="Tema cadastrado")
    assert _importar(_linha(tema=""), diretor).criados == 1


def test_repetido_e_fora_do_aluno(diretor, aluno):
    aluno.corrigir_ingresso(date(2026, 3, 10))
    corpo = _linha() + _linha(data="10/03/2026") + _linha(data="10/03/2026")
    resumo = _importar(corpo, diretor)
    assert [m for _, _, m in resumo.inconsistentes] == [
        "tema de antes do ingresso ou depois da saída do aluno (RN004)",
        "aluno repetido no mesmo tema",
    ]
    assert resumo.criados == 1


def test_ingresso_no_meio_da_semana_do_tema_conta(diretor, aluno):
    aluno.corrigir_ingresso(date(2026, 3, 9))  # segunda da semana do tema de 03/03
    assert _importar(_linha(), diretor).criados == 1


# --- Reimportação com auditoria (NF008, NF009) ---------------------------------------


def test_reimportar_atualiza_com_auditoria(diretor, aluno):
    _importar(_linha(), diretor)
    conferencia = _importar(_linha(notas="200;160;160;160;160;840"), diretor, gravar=False)
    assert conferencia.atualizados == 1 and conferencia.sobreposicoes
    assert ResultadoRedacao.objects.get().nota_c1 == 160
    _importar(_linha(notas="200;160;160;160;160;840"), diretor)
    redacao = ResultadoRedacao.objects.get()
    assert redacao.nota_c1 == 200
    registros = RegistroAlteracao.objects.filter(
        modelo="core.resultadoredacao", objeto_id=str(redacao.pk)
    )
    assert list(registros.values_list("campo", flat=True)) == ["nota_c1"]


# --- Pendências (RN003) --------------------------------------------------------------


def test_pendencia_e_associacao(diretor, aluno):
    resumo = _importar(_linha(matricula="", nome="Aluno Sintético Um"), diretor)
    assert resumo.pendencias == [(2, "Matrícula em branco")] and resumo.temas_criados == 1
    pendencia = PendenciaImportacao.objects.get()
    assert pendencia.origem == "REDACAO" and pendencia.data == TERCA
    assert pendencias.associar([pendencia], aluno, autor=diretor) == (1, [])
    redacao = ResultadoRedacao.objects.get(aluno=aluno)
    assert redacao.nota_total == 800 and redacao.tema == "Tema A"
    resumo = _importar(_linha(matricula="", nome="Aluno Sintético Um"), diretor)
    assert resumo.pendencias == [] and resumo.sem_alteracao == 1
    assert aplicar_pendencia(pendencia, aluno, diretor) == "o aluno já tem redação neste tema"


def test_aplicador_recusa_tema_ausente_e_fora_do_aluno(diretor, aluno):
    dados = {"tema_semana": "2026-03-10", "entregue": False, "notas": [None] * 5}
    assert aplicar_pendencia(PendenciaImportacao(dados=dados), aluno, diretor) == (
        "o tema da redação não está cadastrado"
    )
    TemaRedacao.objects.create(data=date(2026, 1, 6), tema="Tema antigo")
    antes = {**dados, "tema_semana": "2026-01-06"}
    assert "antes do ingresso" in aplicar_pendencia(
        PendenciaImportacao(dados=antes), aluno, diretor
    )


# --- Tela (RN013) --------------------------------------------------------------------

URL = reverse("web:redacoes_importar")


def _montar(corpo):
    def montar(acao):
        arquivo = SimpleUploadedFile("corrija.csv", (CABECALHO + corpo).encode())
        return {"arquivo": arquivo, "ano": 2026, "acao": acao}

    return montar


def test_tela_confere_e_confirma(cliente_diretor, diretor, aluno):
    montar = _montar(_linha() + _linha(matricula="", nome="Sem Matrícula"))
    conferencia = cliente_diretor.post(URL, montar("conferir"))
    html = conferencia.content.decode()
    assert (
        "Pendências para associação manual: 1" in html
        and "Temas criados a partir do arquivo: 1" in html
    )
    assert not ResultadoRedacao.objects.exists() and not TemaRedacao.objects.exists()
    resp = importar_em_dois_passos(cliente_diretor, URL, montar)
    assert resp.context["resultado"].gravado and ResultadoRedacao.objects.count() == 1
    trilha = RegistroImportacao.objects.get()
    assert trilha.tipo == RegistroImportacao.Tipo.REDACOES and trilha.pendencias == 1


def test_tela_so_do_diretor(client, membro, aluno):
    montar = _montar(_linha())
    assert client.post(URL, montar("conferir")).status_code == 302
    client.force_login(membro)
    assert client.post(URL, montar("conferir")).status_code == 403


def test_modelo_para_download_importa(cliente_diretor, diretor):
    ano = date.today().year
    resp = cliente_diretor.get(reverse("web:redacoes_modelo", args=["csv"]))
    linhas = ler_tabela(io.BytesIO(resp.content), "m.csv", colunas=COLUNAS, opcionais=OPCIONAIS)
    turma = Turma.objects.create(nome="Turma A", ano=ano)
    for n in (1, 2):
        Aluno.objects.create(
            matricula=f"S{ano % 100}000{n}", nome="X", data_ingresso=date(ano, 1, 1), turma=turma
        )
    resumo = importar_redacoes(linhas, ano=ano, autor=diretor, gravar=True)
    assert resumo.criados == 2 and not resumo.inconsistentes
    assert cliente_diretor.get(reverse("web:redacoes_modelo", args=["pdf"])).status_code == 404
