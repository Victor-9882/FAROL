"""Importação da frequência da catraca (RF003, RN001, RN003, RN004, RN005, NF006, NF008, NF009).

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
    DiaCalendario,
    PendenciaImportacao,
    PeriodoLetivo,
    RegistroAlteracao,
    RegistroFrequencia,
    RegistroImportacao,
    Turma,
)
from ingestao import pendencias
from ingestao.cadastro import COLUNAS as COLUNAS_CADASTRO
from ingestao.cadastro import importar_cadastro
from ingestao.calendario import TIPOS
from ingestao.frequencia import COLUNAS, OPCIONAIS, aplicar_pendencia, importar_frequencia
from ingestao.leitura import ler_tabela
from tests.conftest import importar_em_dois_passos

pytestmark = pytest.mark.django_db

PASTA = Path(__file__).parent / "dados_sinteticos" / "pequena"
PERFIS = {
    p["perfil"]: p for p in json.loads((PASTA / "perfis_conhecidos.json").read_text())["perfis"]
}
INICIO, FIM = date(2026, 2, 2), date(2026, 11, 27)
SEMANA = date(2026, 3, 2)  # segunda-feira letiva


def _ler(nome, colunas, opcionais=frozenset(), limite=None):
    with (PASTA / "2026" / nome).open("rb") as f:
        return ler_tabela(f, nome, colunas=colunas, opcionais=opcionais, limite_linhas=limite)


def _csv(texto):
    return ler_tabela(io.BytesIO(texto.encode()), "c.csv", colunas=COLUNAS, opcionais=OPCIONAIS)


@pytest.fixture
def ano_2026(diretor):
    """Cadastro e calendário de 2026 da base sintética."""
    importar_cadastro(
        _ler("cadastro_alunos.csv", COLUNAS_CADASTRO, frozenset({"data_ingresso"})),
        ano=2026,
        autor=diretor,
        data_mudanca=date(2026, 6, 25),
        gravar=True,
    )
    PeriodoLetivo.objects.create(inicio=INICIO, fim=FIM, descricao="Ano letivo")
    dias = TIPOS["dias"]
    dias.importar(
        _ler("calendario_letivo.csv", dias.colunas, dias.opcionais),
        ano=2026,
        autor=diretor,
        gravar=True,
    )


@pytest.fixture
def um_aluno(diretor):
    turma = Turma.objects.create(nome="Turma A", ano=2026)
    PeriodoLetivo.objects.create(inicio=INICIO, fim=FIM)
    return Aluno.objects.create(
        matricula="S260001", nome="Aluno Sintético Um", data_ingresso=INICIO, turma=turma
    )


def _importar(linhas, autor, inicio=SEMANA, fim=date(2026, 3, 6), gravar=True):
    return importar_frequencia(linhas, ano=2026, inicio=inicio, fim=fim, autor=autor, gravar=gravar)


def _faltas(matricula):
    return sorted(
        RegistroFrequencia.objects.filter(aluno_id=matricula, presente=False).values_list(
            "data", flat=True
        )
    )


def _d(texto):
    dia, mes, ano = map(int, texto.split("/"))
    return date(ano, mes, dia)


# --- Base sintética do ano todo ------------------------------------------------------


@pytest.mark.regras
def test_ano_sintetico_perfis_conhecidos(diretor, ano_2026):
    linhas = _ler("catraca_presencas.csv", COLUNAS, OPCIONAIS)
    resumo = _importar(linhas, diretor, INICIO, FIM)
    assert resumo.total_linhas == len(linhas)
    assert resumo.dias_letivos == 193
    # RN001: falta é ausência de passagem em dia letivo
    tres = PERFIS["tres_faltas_na_semana"]
    assert _faltas(tres["matricula"]) == [_d(d) for d in tres["esperado"]["datas"]]
    justificada = PERFIS["falta_justificada"]
    assert len(_faltas(justificada["matricula"])) == justificada["esperado"]["ausencias"]
    # RN004: nada antes do ingresso
    chamada = PERFIS["segunda_chamada"]
    ingresso = _d(chamada["esperado"]["data_ingresso"])
    registros = RegistroFrequencia.objects.filter(aluno_id=chamada["matricula"])
    assert registros.exists() and not registros.filter(data__lt=ingresso).exists()
    # RN005: feriados e recessos não entram
    assert not RegistroFrequencia.objects.filter(data=date(2026, 2, 16)).exists()
    assert not RegistroFrequencia.objects.filter(data=date(2026, 7, 6)).exists()
    # RN003: a passagem sem cadastro vira pendência. `S999999` tem o prefixo de ano `99`,
    # então é recusada já pelo formato (outro ano letivo), antes de buscar no cadastro.
    assert resumo.pendencias == [(len(linhas) + 1, "Matrícula de outro ano letivo")]
    pendencia = PendenciaImportacao.objects.get()
    assert pendencia.matricula_informada == "S999999" and pendencia.data == date(2026, 2, 18)


def test_reimportar_o_ano_nao_duplica_e_avisa_sobreposicao(diretor, ano_2026):
    linhas = _ler("catraca_presencas.csv", COLUNAS, OPCIONAIS)
    primeira = _importar(linhas, diretor, INICIO, FIM)
    segunda = _importar(linhas, diretor, INICIO, FIM)
    assert segunda.criados == 0 and segunda.atualizados == 0
    assert segunda.sem_alteracao == primeira.criados
    assert RegistroFrequencia.objects.count() == primeira.criados
    assert segunda.sobreposicoes and "já existem" in segunda.sobreposicoes[0]
    assert PendenciaImportacao.objects.count() == 1  # NF008


# --- Regras (RN001, RN005) -----------------------------------------------------------


@pytest.mark.regras
def test_rn001_sem_tolerancia_uma_passagem_basta_e_nenhuma_e_falta(diretor, um_aluno):
    resumo = _importar(_csv("data;matricula\n02/03/2026 07:59;S260001\n"), diretor)
    assert resumo.presencas == 1 and resumo.faltas == 4
    assert _faltas("S260001") == [date(2026, 3, d) for d in (3, 4, 5, 6)]


@pytest.mark.regras
def test_rn005_passagem_em_dia_nao_letivo_avisa_e_nao_registra(diretor, um_aluno):
    DiaCalendario.objects.create(data=date(2026, 3, 4), letivo=False, descricao="Emenda")
    texto = "data;matricula\n04/03/2026;S260001\n04/03/2026;S260001\n07/03/2026;S260001\n"
    resumo = _importar(_csv(texto), diretor, fim=date(2026, 3, 8))
    assert resumo.dias_letivos == 4 and resumo.passagens_ignoradas == 3
    assert [motivo for _, motivo in resumo.avisos][:2] == [
        "04/03/2026: dia não letivo com 2 passagem(ns); o calendário está atualizado?",
        "07/03/2026: dia não letivo com 1 passagem(ns); o calendário está atualizado?",
    ]
    assert not RegistroFrequencia.objects.filter(data__in=[date(2026, 3, 4), date(2026, 3, 7)])


@pytest.mark.regras
def test_rn005_sabado_letivo_conta(diretor, um_aluno):
    DiaCalendario.objects.create(data=date(2026, 3, 7), letivo=True, descricao="Aula extra")
    resumo = _importar(_csv("data;matricula\n07/03/2026;S260001\n"), diretor, fim=date(2026, 3, 7))
    assert resumo.dias_letivos == 6
    assert RegistroFrequencia.objects.get(data=date(2026, 3, 7)).presente


def test_calendario_definido_ate_antes_do_fim_avisa(diretor, um_aluno):
    PeriodoLetivo.objects.update(fim=date(2026, 3, 4))
    resumo = _importar(_csv("data;matricula\n02/03/2026;S260001\n"), diretor)
    assert resumo.calendario_ate == date(2026, 3, 4) and resumo.dias_letivos == 3
    assert any("calendário definido até 04/03/2026" in m for _, m in resumo.avisos)


def test_sem_periodo_letivo_avisa(diretor):
    resumo = _importar(_csv("data;matricula\n02/03/2026;S260001\n"), diretor)
    assert resumo.dias_letivos == 0 and resumo.passagens_ignoradas == 1
    assert any("nenhum período letivo" in m for _, m in resumo.avisos)


# --- Linhas inconsistentes, repetidas e alunos fora da janela (NF006) -----------------


def test_linhas_inconsistentes_nao_interrompem(diretor, um_aluno):
    texto = (
        "data;matricula\n;S260001\nxx;S260001\n01/03/2027;S260001\n"
        "09/03/2026;S260001\n02/03/2026;S260001\n02/03/2026;S260001\n"
    )
    resumo = _importar(_csv(texto), diretor)
    assert [m for _, _, m in resumo.inconsistentes] == [
        "data em branco",
        "data inválida (use dd/mm/aaaa ou aaaa-mm-dd)",
        "data fora do período informado",
        "data fora do período informado",
    ]
    assert resumo.passagens == 1 and resumo.passagens_ignoradas == 1  # repetida no dia
    assert resumo.total_linhas == 6


def test_aluno_desligado_e_ingresso_limitam_os_registros(diretor, um_aluno):
    um_aluno.situacao, um_aluno.data_saida = Aluno.Situacao.DESLIGADO, date(2026, 3, 3)
    um_aluno.save()
    Aluno.objects.create(
        matricula="S260002", nome="Aluno Dois", data_ingresso=date(2026, 3, 5), turma=um_aluno.turma
    )
    resumo = _importar(_csv("data;matricula\n05/03/2026;S260001\n02/03/2026;S260002\n"), diretor)
    assert sorted(
        RegistroFrequencia.objects.filter(aluno_id="S260001").values_list("data", flat=True)
    ) == [
        date(2026, 3, 2),
        date(2026, 3, 3),
    ]
    assert RegistroFrequencia.objects.filter(aluno_id="S260002").count() == 2
    assert any("antes do ingresso ou depois da saída" in m for _, m in resumo.avisos)


def test_aluno_invalido_vira_pendencia_e_nao_tem_registros(diretor, um_aluno):
    um_aluno.situacao = Aluno.Situacao.INVALIDO
    um_aluno.save()
    resumo = _importar(_csv("data;matricula\n02/03/2026;S260001\n"), diretor)
    assert resumo.pendencias == [(2, "Matrícula de aluno inválido")]
    assert not RegistroFrequencia.objects.exists()


# --- Reimportação substitui com auditoria, sem tocar na justificativa (NF008, NF009, RN002) ---


def test_reimportar_substitui_presenca_audita_e_preserva_justificativa(diretor, um_aluno):
    _importar(_csv("data;matricula\n02/03/2026;S260001\n03/03/2026;S260001\n"), diretor)
    RegistroFrequencia.objects.filter(data=date(2026, 3, 4)).update(justificada=True)
    conferencia = _importar(
        _csv("data;matricula\n02/03/2026;S260001\n04/03/2026;S260001\n"), diretor, gravar=False
    )
    assert conferencia.atualizados == 2 and conferencia.sobreposicoes
    assert RegistroFrequencia.objects.get(data=date(2026, 3, 3)).presente  # nada gravado
    _importar(_csv("data;matricula\n02/03/2026;S260001\n04/03/2026;S260001\n"), diretor)
    assert not RegistroFrequencia.objects.get(data=date(2026, 3, 3)).presente
    quarta = RegistroFrequencia.objects.get(data=date(2026, 3, 4))
    assert quarta.presente and quarta.justificada
    auditados = RegistroAlteracao.objects.filter(modelo="core.registrofrequencia", campo="presente")
    assert auditados.count() == 2 and auditados.filter(autor=diretor).count() == 2


# --- Pendências (RN003) --------------------------------------------------------------


def test_pendencia_associada_vale_como_passagem_na_reimportacao(diretor, um_aluno):
    texto = "data;matricula;nome\n02/03/2026;;Aluno Sintético Um\n02/03/2026;;Aluno Sintético Um\n"
    resumo = _importar(_csv(texto), diretor)
    assert resumo.pendencias == [(2, "Matrícula em branco")]
    assert resumo.passagens_ignoradas == 1  # a mesma pessoa passou duas vezes
    assert not RegistroFrequencia.objects.get(data=SEMANA).presente
    pendencia = PendenciaImportacao.objects.get()
    assert pendencias.associar([pendencia], um_aluno, autor=diretor) == (1, [])
    assert RegistroFrequencia.objects.get(data=SEMANA).presente
    assert RegistroAlteracao.objects.filter(modelo="core.registrofrequencia").count() == 1
    # Reimportar: a pendência já resolvida é ignorada e a presença continua
    resumo = _importar(_csv(texto), diretor)
    assert resumo.pendencias == [] and resumo.passagens_ignoradas == 2
    assert RegistroFrequencia.objects.get(data=SEMANA).presente


def test_aplicador_recusa_dia_nao_letivo_ou_fora_do_aluno(diretor, um_aluno):
    def pendencia_em(dia):
        return PendenciaImportacao(dados={"data": dia.isoformat()})

    assert "não é letivo" in aplicar_pendencia(pendencia_em(date(2026, 3, 7)), um_aluno, diretor)
    assert "antes do ingresso" in aplicar_pendencia(
        pendencia_em(date(2026, 1, 5)), um_aluno, diretor
    )
    assert aplicar_pendencia(pendencia_em(SEMANA), um_aluno, diretor) == ""
    assert RegistroFrequencia.objects.get(data=SEMANA).presente
    assert aplicar_pendencia(pendencia_em(SEMANA), um_aluno, diretor) == ""  # já presente


# --- Tela (RN013) --------------------------------------------------------------------

URL = reverse("web:frequencia_importar")


def _montar(texto, inicio="2026-03-02", fim="2026-03-06", ano=2026):
    def montar(acao):
        return {
            "arquivo": SimpleUploadedFile("catraca.csv", texto.encode()),
            "ano": ano,
            "inicio": inicio,
            "fim": fim,
            "acao": acao,
        }

    return montar


def test_tela_confere_e_confirma(cliente_diretor, diretor, um_aluno):
    montar = _montar("data;matricula\n02/03/2026;S260001\n02/03/2026;S269999\n")
    conferencia = cliente_diretor.post(URL, montar("conferir"))
    assert conferencia.status_code == 200 and not RegistroFrequencia.objects.exists()
    html = conferencia.content.decode()
    assert "Pendências para associação manual: 1" in html and "Faltas: 4" in html
    resp = importar_em_dois_passos(cliente_diretor, URL, montar)
    assert resp.context["resultado"].gravado
    assert RegistroFrequencia.objects.count() == 5
    trilha = RegistroImportacao.objects.get()
    assert trilha.tipo == RegistroImportacao.Tipo.FREQUENCIA and trilha.pendencias == 1
    assert trilha.criados == 5 and trilha.autor == diretor


def test_tela_recusa_periodo_invalido(cliente_diretor, um_aluno):
    texto = "data;matricula\n02/03/2026;S260001\n"
    resp = cliente_diretor.post(URL, _montar(texto, fim="2026-03-01")("conferir"))
    assert "não pode ser anterior" in resp.content.decode()
    resp = cliente_diretor.post(URL, _montar(texto, fim="2027-01-08")("conferir"))
    assert "dentro do ano letivo" in resp.content.decode()
    assert not RegistroFrequencia.objects.exists()


def test_tela_so_do_diretor(client, membro, um_aluno):
    montar = _montar("data;matricula\n02/03/2026;S260001\n")
    assert client.post(URL, montar("conferir")).status_code == 302
    client.force_login(membro)
    assert client.post(URL, montar("conferir")).status_code == 403
    assert not RegistroFrequencia.objects.exists()


def test_modelo_para_download_usa_o_ano_atual(client, membro):
    client.force_login(membro)
    resp = client.get(reverse("web:frequencia_modelo", args=["csv"]))
    texto = resp.content.decode("utf-8-sig")
    assert texto.splitlines()[0] == "data;matricula;nome"
    assert f"/{date.today().year};S{date.today().year % 100}0001" in texto
    assert client.get(reverse("web:frequencia_modelo", args=["pdf"])).status_code == 404


def test_limite_de_linhas_da_catraca(settings, cliente_diretor, um_aluno):
    settings.IMPORTACAO_LIMITE_LINHAS_CATRACA = 2
    texto = "data;matricula\n" + "02/03/2026;S260001\n" * 3
    resp = cliente_diretor.post(URL, _montar(texto)("conferir"))
    assert "limite de 2 linhas" in resp.content.decode()
