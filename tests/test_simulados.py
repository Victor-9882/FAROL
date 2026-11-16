"""Importação dos resultados de simulados do P+ (RF004, RN003, RN004, RN006, RN009, RN010).

Só dados sintéticos (NF017): a base `pequena/2026` e linhas inventadas.
"""

import io
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import (
    Aluno,
    CicloCalendario,
    PendenciaImportacao,
    RegistroAlteracao,
    RegistroImportacao,
    ResultadoSimulado,
    Turma,
)
from ingestao import pendencias
from ingestao.cadastro import COLUNAS as COLUNAS_CADASTRO
from ingestao.cadastro import importar_cadastro
from ingestao.calendario import TIPOS
from ingestao.leitura import ler_tabela
from ingestao.simulados import COLUNAS, OPCIONAIS, aplicar_pendencia, importar_simulados
from tests.conftest import importar_em_dois_passos

pytestmark = pytest.mark.django_db

PASTA = Path(__file__).parent / "dados_sinteticos" / "pequena"
PERFIS = {
    p["perfil"]: p for p in json.loads((PASTA / "perfis_conhecidos.json").read_text())["perfis"]
}
Area = ResultadoSimulado.Area
CABECALHO = (
    "data;matricula;nome;presenca;"
    "LC_acertos;LC_tri;CH_acertos;CH_tri;CN_acertos;CN_tri;MT_acertos;MT_tri\n"
)


def _ler(nome, colunas, opcionais=frozenset()):
    with (PASTA / "2026" / nome).open("rb") as f:
        return ler_tabela(f, nome, colunas=colunas, opcionais=opcionais)


def _csv(corpo):
    texto = CABECALHO + corpo
    return ler_tabela(io.BytesIO(texto.encode()), "p.csv", colunas=COLUNAS, opcionais=OPCIONAIS)


def _linha(
    matricula="S260001",
    presenca="Presente",
    notas="30;650,0;30;650,0;30;650,0;30;650,0",
    data="15/03/2026",
    nome="Aluno Sintético Um",
):
    return f"{data};{matricula};{nome};{presenca};{notas}\n"


AUSENTE = ";;;;;;;"


@pytest.fixture
def ano_2026(diretor):
    importar_cadastro(
        _ler("cadastro_alunos.csv", COLUNAS_CADASTRO, frozenset({"data_ingresso"})),
        ano=2026,
        autor=diretor,
        data_mudanca=date(2026, 6, 25),
        gravar=True,
    )
    ciclos = TIPOS["ciclos"]
    ciclos.importar(
        _ler("ciclos.csv", ciclos.colunas, ciclos.opcionais), ano=2026, autor=diretor, gravar=True
    )


@pytest.fixture
def ciclo(db):
    return CicloCalendario.objects.create(
        data_inicio=date(2026, 3, 2), data_fim=date(2026, 3, 15), data_simulado=date(2026, 3, 15)
    )


@pytest.fixture
def aluno(ciclo):
    turma = Turma.objects.create(nome="Turma A", ano=2026)
    return Aluno.objects.create(
        matricula="S260001", nome="Aluno Sintético Um", data_ingresso=date(2026, 2, 2), turma=turma
    )


def _importar(corpo, autor, gravar=True):
    return importar_simulados(_csv(corpo), ano=2026, autor=autor, gravar=gravar)


# --- Base sintética do ano todo ------------------------------------------------------


@pytest.mark.regras
def test_ano_sintetico_perfis_conhecidos(diretor, ano_2026):
    linhas = _ler("p_mais_simulados.csv", COLUNAS, OPCIONAIS)
    resumo = importar_simulados(linhas, ano=2026, autor=diretor, gravar=True)
    assert resumo.total_linhas == len(linhas) and not resumo.inconsistentes
    assert ResultadoSimulado.objects.count() == 4 * len(linhas)
    # RN009: ausência registrada, sem nota
    ausente = PERFIS["ausente_no_simulado"]
    data = date(2026, 4, 26)
    assert ausente["esperado"]["data_simulado"] == "26/04/2026"
    faltou = ResultadoSimulado.objects.filter(
        aluno_id=ausente["matricula"], ciclo__data_simulado=data
    )
    assert faltou.count() == 4 and not faltou.filter(presente=True).exists()
    assert not faltou.exclude(nota_tri__isnull=True).exists()
    assert resumo.ausentes == 24
    # RN010: nota TRI e acertos por área; queda de 650 para 590 no ciclo 8
    queda = PERFIS["queda_de_desempenho"]
    notas = list(
        ResultadoSimulado.objects.filter(aluno_id=queda["matricula"], area=Area.MATEMATICA)
        .order_by("ciclo__data_inicio")
        .values_list("nota_tri", flat=True)
    )
    assert notas[6] == Decimal("650.0") and notas[7] == Decimal("590.0")
    assert ResultadoSimulado.objects.filter(acertos__isnull=False).exists()


def test_reimportar_nao_duplica_e_avisa(diretor, ano_2026):
    linhas = _ler("p_mais_simulados.csv", COLUNAS, OPCIONAIS)
    importar_simulados(linhas, ano=2026, autor=diretor, gravar=True)
    segunda = importar_simulados(linhas, ano=2026, autor=diretor, gravar=True)
    assert segunda.sem_alteracao == len(linhas) and segunda.importados == 0
    assert ResultadoSimulado.objects.count() == 4 * len(linhas)
    assert segunda.sobreposicoes and "já têm resultado" in segunda.sobreposicoes[0]


# --- Regras e valores-limite (RN009, RN010) ------------------------------------------


@pytest.mark.regras
def test_rn009_ausente_sem_nota_e_presente_com_nota(diretor, aluno):
    turma = aluno.turma
    Aluno.objects.create(
        matricula="S260002", nome="Dois", data_ingresso=date(2026, 2, 2), turma=turma
    )
    resumo = _importar(_linha() + _linha("S260002", "Ausente", AUSENTE), diretor)
    assert resumo.criados == 2 and resumo.ausentes == 1
    um = ResultadoSimulado.objects.get(aluno=aluno, area=Area.LINGUAGENS)
    assert um.presente and um.acertos == 30 and um.nota_tri == Decimal("650.0")
    dois = ResultadoSimulado.objects.filter(aluno_id="S260002")
    assert dois.count() == 4 and all(not r.presente and r.nota_tri is None for r in dois)


@pytest.mark.regras
@pytest.mark.parametrize(
    "presenca,notas,motivo",
    [
        ("Ausente", "30;650,0" + ";;;;;;", "aluno ausente com nota (RN009)"),
        (
            "Presente",
            ";650,0;30;650,0;30;650,0;30;650,0",
            "nota de LC em branco para aluno presente",
        ),
        ("Talvez", AUSENTE, "presença inválida (use Presente ou Ausente)"),
        ("Presente", "46;650,0;30;650,0;30;650,0;30;650,0", "acertos de LC fora de 0 a 45"),
        ("Presente", "-1;650,0;30;650,0;30;650,0;30;650,0", "acertos de LC fora de 0 a 45"),
        ("Presente", "30;1000,1;30;650,0;30;650,0;30;650,0", "nota TRI de LC fora de 0 a 1000"),
        ("Presente", "30;abc;30;650,0;30;650,0;30;650,0", "nota TRI de LC fora de 0 a 1000"),
    ],
)
def test_linhas_invalidas(diretor, aluno, presenca, notas, motivo):
    resumo = _importar(_linha(presenca=presenca, notas=notas), diretor)
    assert [m for _, _, m in resumo.inconsistentes] == [motivo]
    assert not ResultadoSimulado.objects.exists()


@pytest.mark.regras
def test_valores_limite_aceitos(diretor, aluno):
    resumo = _importar(_linha(notas="0;0;45;1000;45;1000,0;0;0,0"), diretor)
    assert resumo.criados == 1 and not resumo.inconsistentes
    assert ResultadoSimulado.objects.get(area=Area.HUMANAS).nota_tri == Decimal("1000.0")


def test_data_ciclo_e_aluno(diretor, aluno):
    corpo = (
        _linha(data="")
        + _linha(data="xx")
        + _linha(data="15/03/2025")
        + _linha(data="20/03/2026")  # sem ciclo
        + _linha(data="10/03/2026")  # dentro do ciclo, fora da data do simulado
        + _linha(data="15/03/2026")  # repetido no mesmo ciclo
    )
    resumo = _importar(corpo, diretor)
    assert [m for _, _, m in resumo.inconsistentes] == [
        "data do simulado em branco",
        "data do simulado inválida (use dd/mm/aaaa ou aaaa-mm-dd)",
        "data do simulado fora do ano letivo informado",
        "nenhum ciclo do calendário contém a data do simulado (RN006)",
        "aluno repetido no mesmo simulado",
    ]
    assert resumo.criados == 1 and resumo.total_linhas == 6


def test_simulado_antes_do_ingresso_e_inconsistente(diretor, aluno):
    aluno.corrigir_ingresso(date(2026, 3, 20))
    resumo = _importar(_linha(), diretor)
    assert "antes do ingresso" in resumo.inconsistentes[0][2]


# --- Reimportação com auditoria (NF008, NF009) ---------------------------------------


def test_reimportar_atualiza_com_auditoria(diretor, aluno):
    _importar(_linha(), diretor)
    conferencia = _importar(
        _linha(notas="31;660,5;30;650,0;30;650,0;30;650,0"), diretor, gravar=False
    )
    assert conferencia.atualizados == 1 and conferencia.sobreposicoes
    assert ResultadoSimulado.objects.get(area=Area.LINGUAGENS).acertos == 30  # nada gravado
    _importar(_linha(notas="31;660,5;30;650,0;30;650,0;30;650,0"), diretor)
    lc = ResultadoSimulado.objects.get(area=Area.LINGUAGENS)
    assert lc.acertos == 31 and lc.nota_tri == Decimal("660.5")
    campos = set(
        RegistroAlteracao.objects.filter(objeto_id=str(lc.pk)).values_list("campo", flat=True)
    )
    assert campos == {"acertos", "nota_tri"}


# --- Pendências (RN003) --------------------------------------------------------------


def test_pendencia_e_associacao(diretor, aluno):
    resumo = _importar(_linha(matricula="", nome="Aluno Sintético Um"), diretor)
    assert resumo.pendencias == [(2, "Matrícula em branco")]
    assert not ResultadoSimulado.objects.exists()
    pendencia = PendenciaImportacao.objects.get()
    assert pendencia.origem == "SIMULADO" and pendencia.dados["ciclo"] == _ciclo_pk()
    assert pendencias.associar([pendencia], aluno, autor=diretor) == (1, [])
    assert ResultadoSimulado.objects.filter(aluno=aluno).count() == 4
    assert ResultadoSimulado.objects.get(area=Area.MATEMATICA).nota_tri == Decimal("650.0")
    # reimportar: pendência resolvida não volta nem duplica
    resumo = _importar(_linha(matricula="", nome="Aluno Sintético Um"), diretor)
    assert resumo.pendencias == [] and resumo.sem_alteracao == 1
    # o aluno já tem resultado: outra pendência do mesmo simulado é recusada
    outra = PendenciaImportacao(
        dados={"ciclo": pendencia.dados["ciclo"], "presente": False, "notas": {}},
        data=pendencia.data,
    )
    assert aplicar_pendencia(outra, aluno, diretor) == "o aluno já tem resultado neste simulado"


def _ciclo_pk():
    return CicloCalendario.objects.get().pk


def test_aplicador_recusa_ciclo_inexistente_e_fora_do_aluno(diretor, aluno):
    sem_ciclo = PendenciaImportacao(
        dados={"ciclo": 999, "presente": False, "notas": {}}, data=date(2026, 3, 15)
    )
    assert aplicar_pendencia(sem_ciclo, aluno, diretor) == "o ciclo do simulado não existe mais"
    antes = PendenciaImportacao(
        dados={"ciclo": _ciclo_pk(), "presente": False, "notas": {}}, data=date(2026, 1, 15)
    )
    assert "antes do ingresso" in aplicar_pendencia(antes, aluno, diretor)


# --- Datas do ciclo são fixas depois dos resultados ----------------------------------


def test_ciclo_com_resultados_nao_muda_de_data(diretor, aluno, ciclo):
    ciclo.data_fim = date(2026, 3, 16)
    ciclo.full_clean()  # sem resultados: pode
    ciclo.data_fim = date(2026, 3, 15)
    _importar(_linha(), diretor)
    ciclo.data_simulado = date(2026, 3, 14)
    with pytest.raises(ValidationError, match="datas do ciclo são fixas"):
        ciclo.full_clean()
    # pela importação do calendário: a linha é recusada
    tipo = TIPOS["ciclos"]
    texto = "data_inicio;data_fim;data_simulado\n02/03/2026;15/03/2026;14/03/2026\n"
    linhas = ler_tabela(
        io.BytesIO(texto.encode()), "c.csv", colunas=tipo.colunas, opcionais=tipo.opcionais
    )
    resumo = tipo.importar(linhas, ano=2026, autor=diretor, gravar=True)
    assert "datas do ciclo são fixas" in resumo.inconsistentes[0][1]
    assert CicloCalendario.objects.get().data_simulado == date(2026, 3, 15)


def test_tela_do_calendario_recusa_mudar_ciclo_com_resultados(
    cliente_diretor, diretor, aluno, ciclo
):
    _importar(_linha(), diretor)
    url = reverse("web:calendario_item", args=["ciclos", ciclo.pk])
    resp = cliente_diretor.post(
        url, {"data_inicio": "2026-03-02", "data_fim": "2026-03-16", "data_simulado": "2026-03-15"}
    )
    assert resp.status_code == 200 and "datas do ciclo são fixas" in resp.content.decode()
    ciclo.refresh_from_db()
    assert ciclo.data_fim == date(2026, 3, 15)


# --- Tela (RN013) --------------------------------------------------------------------

URL = reverse("web:simulados_importar")


def _montar(corpo):
    def montar(acao):
        arquivo = SimpleUploadedFile("pmais.csv", (CABECALHO + corpo).encode())
        return {"arquivo": arquivo, "ano": 2026, "acao": acao}

    return montar


def test_tela_confere_e_confirma(cliente_diretor, diretor, aluno):
    montar = _montar(_linha() + _linha(matricula="S269999"))
    conferencia = cliente_diretor.post(URL, montar("conferir"))
    assert "Pendências para associação manual: 1" in conferencia.content.decode()
    assert not ResultadoSimulado.objects.exists()
    resp = importar_em_dois_passos(cliente_diretor, URL, montar)
    assert resp.context["resultado"].gravado and ResultadoSimulado.objects.count() == 4
    trilha = RegistroImportacao.objects.get()
    assert trilha.tipo == RegistroImportacao.Tipo.SIMULADOS and trilha.pendencias == 1


def test_tela_so_do_diretor(client, membro, aluno):
    montar = _montar(_linha())
    assert client.post(URL, montar("conferir")).status_code == 302
    client.force_login(membro)
    assert client.post(URL, montar("conferir")).status_code == 403


def test_modelo_para_download_importa(cliente_diretor, diretor):
    ano = date.today().year
    resp = cliente_diretor.get(reverse("web:simulados_modelo", args=["csv"]))
    texto = resp.content.decode("utf-8-sig")
    assert f"S{ano % 100}0001" in texto and "Ausente" in texto
    linhas = ler_tabela(io.BytesIO(resp.content), "m.csv", colunas=COLUNAS, opcionais=OPCIONAIS)
    turma = Turma.objects.create(nome="Turma A", ano=ano)
    for n in (1, 2):
        Aluno.objects.create(
            matricula=f"S{ano % 100}000{n}", nome="X", data_ingresso=date(ano, 1, 1), turma=turma
        )
    CicloCalendario.objects.create(
        data_inicio=date(ano, 3, 2), data_fim=date(ano, 3, 15), data_simulado=date(ano, 3, 15)
    )
    resumo = importar_simulados(linhas, ano=ano, autor=diretor, gravar=True)
    assert resumo.criados == 2 and not resumo.inconsistentes
    assert cliente_diretor.get(reverse("web:simulados_modelo", args=["pdf"])).status_code == 404
