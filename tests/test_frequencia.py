"""Importação da frequência pela grade "Presença Anual" (RF003, RN001, RN002, RN003, RN004,
RN005, NF006, NF008, NF009).

Só dados sintéticos (NF017): a réplica `pequena/2026/planilhas/presenca_anual.xlsx` e grades
montadas no mesmo layout por `ingestao.planilhas_casd`.
"""

import io
import json
from datetime import date
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

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
from ingestao import pendencias, planilhas_casd
from ingestao.cadastro import COLUNAS as COLUNAS_CADASTRO
from ingestao.cadastro import importar_cadastro
from ingestao.calendario import TIPOS
from ingestao.frequencia import aplicar_pendencia, importar_frequencia, ler_grade
from ingestao.justificativas import justificar
from ingestao.leitura import ArquivoInvalidoError, ler_tabela
from tests.conftest import importar_em_dois_passos

pytestmark = pytest.mark.django_db

PASTA = Path(__file__).parent / "dados_sinteticos" / "pequena"
REPLICA = PASTA / "2026" / "planilhas" / "presenca_anual.xlsx"
PERFIS = {
    p["perfil"]: p for p in json.loads((PASTA / "perfis_conhecidos.json").read_text())["perfis"]
}
INICIO, FIM = date(2026, 2, 2), date(2026, 11, 27)
SEG = date(2026, 3, 2)  # segunda-feira letiva
UM = {"nome": "Aluno Sintético Um", "matricula": "S260001", "turma": "Turma 1"}


def _d(texto):
    dia, mes, ano = map(int, texto.split("/"))
    return date(ano, mes, dia)


def _ler_csv(nome, colunas, opcionais=frozenset()):
    with (PASTA / "2026" / nome).open("rb") as f:
        return ler_tabela(f, nome, colunas=colunas, opcionais=opcionais)


def _grade(alunos, codigos, ano=2026):
    """Grade no layout real, lida como o FAROL lê."""
    conteudo = planilhas_casd.grade_presenca(ano, alunos, codigos)
    return ler_grade(io.BytesIO(conteudo), "Controle de Presença.xlsx", ano=ano)


def _semana(matricula, codigos, segunda=SEG):
    return {
        (matricula, date.fromordinal(segunda.toordinal() + i)): c for i, c in enumerate(codigos)
    }


def _importar(grade, autor, gravar=True):
    return importar_frequencia(grade, ano=2026, autor=autor, gravar=gravar)


def _registros(matricula):
    return {
        r.data: ("J" if r.justificada else "P" if r.presente else "F")
        for r in RegistroFrequencia.objects.filter(aluno_id=matricula)
    }


@pytest.fixture
def ano_2026(diretor):
    """Cadastro e calendário de 2026 da base sintética."""
    importar_cadastro(
        _ler_csv("cadastro_alunos.csv", COLUNAS_CADASTRO, frozenset({"data_ingresso"})),
        ano=2026,
        autor=diretor,
        data_mudanca=date(2026, 6, 25),
        gravar=True,
    )
    PeriodoLetivo.objects.create(inicio=INICIO, fim=FIM, descricao="Ano letivo")
    dias = TIPOS["dias"]
    dias.importar(
        _ler_csv("calendario_letivo.csv", dias.colunas, dias.opcionais),
        ano=2026,
        autor=diretor,
        gravar=True,
    )


@pytest.fixture
def um_aluno(db):
    turma = Turma.objects.create(nome="Turma 1", ano=2026)
    PeriodoLetivo.objects.create(inicio=INICIO, fim=FIM)
    return Aluno.objects.create(
        matricula="S260001", nome=UM["nome"], data_ingresso=INICIO, turma=turma
    )


# --- Réplica do ano todo -------------------------------------------------------------


@pytest.mark.regras
def test_replica_do_ano_perfis_conhecidos(diretor, ano_2026):
    grade = ler_grade(REPLICA.open("rb"), REPLICA.name, ano=2026)
    resumo = _importar(grade, diretor)
    assert resumo.total_linhas == len(grade.linhas) == 21
    assert resumo.dias_letivos == 193 and resumo.calendario_ate == FIM
    # RN001: F na grade (sem passagem na catraca) é falta
    tres = PERFIS["tres_faltas_na_semana"]
    faltas = sorted(d for d, c in _registros(tres["matricula"]).items() if c == "F")
    assert faltas == [_d(d) for d in tres["esperado"]["datas"]]
    # RN002: J é falta justificada
    justificada = PERFIS["falta_justificada"]
    codigos = _registros(justificada["matricula"])
    assert codigos[_d(justificada["esperado"]["data_justificada"])] == "J"
    assert (
        sum(c == "F" for c in codigos.values())
        == justificada["esperado"]["faltas_nao_justificadas"]
    )
    # RN004: nada antes do ingresso
    chamada = PERFIS["segunda_chamada"]
    assert min(_registros(chamada["matricula"])) == _d(chamada["esperado"]["data_ingresso"])
    # RN005: S (feriado, recesso) não vira registro
    assert not RegistroFrequencia.objects.filter(data__in=[date(2026, 2, 16), date(2026, 7, 6)])
    # RN003: a linha da passagem sem cadastro vira pendência
    assert [m for _, m in resumo.pendencias] == ["Matrícula de outro ano letivo"]
    assert PendenciaImportacao.objects.get().matricula_informada == "S999999"


def test_reimportar_a_replica_nao_duplica(diretor, ano_2026):
    grade = ler_grade(REPLICA.open("rb"), REPLICA.name, ano=2026)
    primeira = _importar(grade, diretor)
    segunda = _importar(grade, diretor)
    assert segunda.registros_criados == 0 and segunda.registros_alterados == 0
    assert segunda.registros_iguais == primeira.registros_criados
    assert segunda.sem_alteracao == 20 and segunda.sobreposicoes
    assert PendenciaImportacao.objects.count() == 1  # NF008


# --- Códigos P, F, J e S (RN001, RN002, RN005) -----------------------------------------


@pytest.mark.regras
def test_codigos_p_f_j_e_s(diretor, um_aluno):
    resumo = _importar(_grade([UM], _semana("S260001", "PFJSP")), diretor)
    assert _registros("S260001") == {
        date(2026, 3, 2): "P",
        date(2026, 3, 3): "F",
        date(2026, 3, 4): "J",
        date(2026, 3, 6): "P",
    }
    assert (resumo.presencas, resumo.faltas, resumo.justificadas) == (2, 1, 1)
    assert any(
        "05/03/2026: dia letivo no calendário, mas a grade marca S" in m for _, m in resumo.avisos
    )


@pytest.mark.regras
def test_rn005_registro_em_dia_nao_letivo_avisa_e_nao_entra(diretor, um_aluno):
    DiaCalendario.objects.create(data=date(2026, 3, 4), letivo=False, descricao="Emenda")
    resumo = _importar(_grade([UM], _semana("S260001", "PPPPP")), diretor)
    assert date(2026, 3, 4) not in _registros("S260001") and len(_registros("S260001")) == 4
    assert any(
        "04/03/2026: dia não letivo no calendário com 1 registro(s)" in m for _, m in resumo.avisos
    )


def test_avisos_de_calendario_e_codigos(diretor, um_aluno):
    PeriodoLetivo.objects.update(fim=date(2026, 3, 4))
    codigos = _semana("S260001", "PPPPP") | {("S260001", date(2026, 3, 9)): "X"}
    resumo = _importar(_grade([UM], codigos), diretor)
    mensagens = " | ".join(m for _, m in resumo.avisos)
    assert "calendário definido até 04/03/2026" in mensagens
    assert "1 célula(s) de dia com código desconhecido" in mensagens


def test_dias_letivos_sem_coluna_na_grade_avisam(diretor, um_aluno):
    codigos = {("S260001", SEG): "P", ("S260001", date(2026, 3, 13)): "P"}
    grade = _grade([UM], codigos)
    grade.datas = [d for d in grade.datas if d.isoweekday() in (1, 5)]  # sem as colunas do meio
    resumo = _importar(grade, diretor)
    assert any("dia(s) letivo(s) do calendário sem coluna na grade" in m for _, m in resumo.avisos)


def test_sem_periodo_letivo_avisa(diretor):
    turma = Turma.objects.create(nome="Turma 1", ano=2026)
    Aluno.objects.create(matricula="S260001", nome="A", data_ingresso=INICIO, turma=turma)
    resumo = _importar(_grade([UM], _semana("S260001", "P")), diretor)
    assert resumo.dias_letivos == 0 and not RegistroFrequencia.objects.exists()
    assert any("nenhum período letivo" in m for _, m in resumo.avisos)


def test_janela_do_aluno(diretor, um_aluno):
    um_aluno.situacao, um_aluno.data_saida = Aluno.Situacao.DESLIGADO, date(2026, 3, 3)
    um_aluno.save()
    resumo = _importar(_grade([UM], _semana("S260001", "PPPPP")), diretor)
    assert sorted(_registros("S260001")) == [date(2026, 3, 2), date(2026, 3, 3)]
    assert any("3 registro(s) antes do ingresso ou depois da saída" in m for _, m in resumo.avisos)


# --- Leitura da grade ----------------------------------------------------------------


def _xlsx(linhas):
    livro = Workbook()
    for linha in linhas:
        livro.active.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    saida.seek(0)
    return saida


def test_grade_sem_matricula_e_recusada():
    arquivo = _xlsx([["Nome", "Turma", date(2026, 3, 2)], ["Aluno", "Turma 1", "P"]])
    with pytest.raises(ArquivoInvalidoError, match="acrescente a coluna Matrícula"):
        ler_grade(arquivo, "g.xlsx", ano=2026)


def test_grade_com_datas_em_texto_como_no_nivelamento(diretor, um_aluno):
    arquivo = _xlsx(
        [
            [None, None, "Controle de Presença"],
            ["Nome", "Matrícula", "Turma", "02/03", "03/03", "Faltas", "31/12/2025"],
            ["Aluno", 2630001.0, "Turma 1", "P", "f", 1, "P"],
            ["Aluno", "S260001", "Turma 1", "P", "f", 1, "P"],
            [None, None, "Média T1", "P"],  # linha de totais: pulada
        ]
    )
    grade = ler_grade(arquivo, "g.xlsx", ano=2026)
    assert grade.datas == [date(2026, 3, 2), date(2026, 3, 3)] and grade.colunas_de_outro_ano == 1
    assert [linha["matricula"] for linha in grade.linhas] == ["2630001", "S260001"]
    _importar(grade, diretor)
    assert _registros("S260001") == {date(2026, 3, 2): "P", date(2026, 3, 3): "F"}


def test_grade_sem_colunas_do_ano_sem_alunos_e_aba_inexistente():
    arquivo = _xlsx([["Nome", "Matrícula", date(2025, 3, 3)], ["A", "S260001", "P"]])
    with pytest.raises(ArquivoInvalidoError, match="colunas de dia do ano"):
        ler_grade(arquivo, "g.xlsx", ano=2026)
    arquivo = _xlsx([["Nome", "Matrícula", date(2026, 3, 3)], [None, None, "-"]])
    with pytest.raises(ArquivoInvalidoError, match="linhas de aluno"):
        ler_grade(arquivo, "g.xlsx", ano=2026)
    with pytest.raises(ArquivoInvalidoError, match="não existe no arquivo"):
        ler_grade(REPLICA.open("rb"), REPLICA.name, ano=2026, aba="Nivelamento")


def test_aluno_repetido_na_grade(diretor, um_aluno):
    resumo = _importar(_grade([UM, UM], _semana("S260001", "PPPPP")), diretor)
    assert resumo.inconsistentes == [(5, "S260001", "aluno repetido na grade")]


# --- Reimportação substitui, com auditoria (NF008, NF009) ----------------------------


def test_reimportar_substitui_e_audita(diretor, um_aluno):
    _importar(_grade([UM], _semana("S260001", "PFPPP")), diretor)
    conferencia = _importar(_grade([UM], _semana("S260001", "PJPFP")), diretor, gravar=False)
    assert conferencia.registros_alterados == 2 and conferencia.sobreposicoes
    assert _registros("S260001")[date(2026, 3, 3)] == "F"  # nada gravado
    _importar(_grade([UM], _semana("S260001", "PJPFP")), diretor)
    assert _registros("S260001")[date(2026, 3, 3)] == "J"
    assert _registros("S260001")[date(2026, 3, 5)] == "F"
    campos = RegistroAlteracao.objects.filter(modelo="core.registrofrequencia")
    assert sorted(campos.values_list("campo", flat=True)) == ["justificada", "presente"]


# D5 (pergunta B1, provisória): o F da grade não desfaz a justificativa registrada no FAROL
# (RF008). Para reverter, ver `ingestao.frequencia._mantem_justificada`.


@pytest.mark.regras
def test_reimportar_f_nao_desfaz_justificativa(diretor, um_aluno):
    _importar(_grade([UM], _semana("S260001", "PFPPP")), diretor)
    terca = date(2026, 3, 3)
    registro = RegistroFrequencia.objects.get(aluno=um_aluno, data=terca)
    assert justificar(registro, autor=diretor)
    auditorias = RegistroAlteracao.objects.count()
    resumo = _importar(_grade([UM], _semana("S260001", "PFPPP")), diretor)
    assert _registros("S260001")[terca] == "J"
    assert resumo.registros_alterados == 0
    assert (resumo.justificadas, resumo.faltas, resumo.justificativas_mantidas) == (1, 0, 1)
    assert any("1 falta(s) já justificada(s) no FAROL" in aviso for _, aviso in resumo.avisos)
    assert RegistroAlteracao.objects.count() == auditorias


def test_justificativa_mantida_entra_na_assinatura(diretor, um_aluno):
    _importar(_grade([UM], _semana("S260001", "PFPPP")), diretor)
    sem = _importar(_grade([UM], _semana("S260001", "PFPPP")), diretor, gravar=False)
    justificar(RegistroFrequencia.objects.get(aluno=um_aluno, data=date(2026, 3, 3)), autor=diretor)
    com = _importar(_grade([UM], _semana("S260001", "PFPPP")), diretor, gravar=False)
    assert sem.assinatura() != com.assinatura()


def test_reimportar_p_sobre_justificada_vale_a_grade(diretor, um_aluno):
    _importar(_grade([UM], _semana("S260001", "PFPPP")), diretor)
    terca = date(2026, 3, 3)
    registro = RegistroFrequencia.objects.get(aluno=um_aluno, data=terca)
    justificar(registro, autor=diretor)
    resumo = _importar(_grade([UM], _semana("S260001", "PPPPP")), diretor)
    assert _registros("S260001")[terca] == "P" and resumo.registros_alterados == 1
    assert resumo.justificativas_mantidas == 0
    ultima = RegistroAlteracao.objects.filter(objeto_id=str(registro.pk)).order_by("-pk")
    assert {(a.campo, a.valor_anterior, a.valor_novo) for a in ultima[:2]} == {
        ("presente", "False", "True"),
        ("justificada", "True", "False"),
    }


def test_pendencia_associada_nao_desfaz_justificativa(diretor, um_aluno):
    registro = RegistroFrequencia.objects.create(
        aluno=um_aluno, data=SEG, presente=False, justificada=True
    )
    pendencia = PendenciaImportacao(dados={"codigos": {"2026-03-02": "F"}})
    assert aplicar_pendencia(pendencia, um_aluno, diretor) == ""
    registro.refresh_from_db()
    assert registro.justificada is True and not RegistroAlteracao.objects.exists()


# --- Pendências (RN003) --------------------------------------------------------------


def test_pendencia_associada_vale_nas_reimportacoes(diretor, um_aluno):
    sem_matricula = {"nome": UM["nome"], "matricula": "", "turma": "Turma 1"}
    resumo = _importar(_grade([sem_matricula], _semana("", "PFPPP")), diretor)
    assert resumo.pendencias == [(4, "Matrícula em branco")]
    pendencia = PendenciaImportacao.objects.get()
    assert pendencias.associar([pendencia], um_aluno, autor=diretor) == (1, [])
    assert _registros("S260001")[date(2026, 3, 3)] == "F"
    # a grade da semana seguinte, ainda sem matrícula, vale para o aluno associado
    codigos = _semana("", "PFPPP") | _semana("", "PPPPJ", date(2026, 3, 9))
    resumo = _importar(_grade([sem_matricula], codigos), diretor)
    assert resumo.pendencias == [] and resumo.atualizados == 1
    assert _registros("S260001")[date(2026, 3, 13)] == "J"
    assert PendenciaImportacao.objects.count() == 1


def test_pendencia_descartada_e_ignorada(diretor, um_aluno):
    sem_matricula = {"nome": "Desconhecido", "matricula": "", "turma": ""}
    _importar(_grade([sem_matricula], _semana("", "P")), diretor)
    pendencias.descartar(list(PendenciaImportacao.objects.all()), autor=diretor)
    resumo = _importar(_grade([sem_matricula], _semana("", "P")), diretor)
    assert resumo.pendencias == [] and resumo.sem_alteracao == 1


def test_aplicador_sem_dia_aplicavel_e_com_alteracao(diretor, um_aluno):
    pendencia = PendenciaImportacao(dados={"codigos": {"2026-03-07": "P", "2026-03-02": "S"}})
    assert "nenhum dia" in aplicar_pendencia(pendencia, um_aluno, diretor)
    RegistroFrequencia.objects.create(aluno=um_aluno, data=SEG, presente=False)
    pendencia = PendenciaImportacao(dados={"codigos": {"2026-03-02": "P", "2026-03-03": "J"}})
    assert aplicar_pendencia(pendencia, um_aluno, diretor) == ""
    assert _registros("S260001") == {SEG: "P", date(2026, 3, 3): "J"}
    registro = RegistroFrequencia.objects.get(data=SEG)
    assert RegistroAlteracao.objects.filter(objeto_id=str(registro.pk), campo="presente").exists()


# --- Tela (RN013) --------------------------------------------------------------------

URL = reverse("web:frequencia_importar")


def _montar(conteudo, aba=""):
    def montar(acao):
        arquivo = SimpleUploadedFile("Controle de Presença 2026.xlsx", conteudo)
        return {"arquivo": arquivo, "ano": 2026, "aba": aba, "acao": acao}

    return montar


def test_tela_confere_e_confirma_a_replica(cliente_diretor, diretor, ano_2026):
    montar = _montar(REPLICA.read_bytes())
    conferencia = cliente_diretor.post(URL, montar("conferir"))
    html = conferencia.content.decode()
    assert "Pendências para associação manual: 1" in html and "Faltas justificadas:" in html
    assert not RegistroFrequencia.objects.exists()
    resp = importar_em_dois_passos(cliente_diretor, URL, montar)
    assert resp.context["resultado"].gravado and RegistroFrequencia.objects.exists()
    trilha = RegistroImportacao.objects.get()
    assert trilha.tipo == RegistroImportacao.Tipo.FREQUENCIA and trilha.pendencias == 1


def test_tela_mostra_erro_de_leitura(cliente_diretor, um_aluno):
    resp = cliente_diretor.post(URL, _montar(REPLICA.read_bytes(), aba="Nivelamento")("conferir"))
    assert "não existe no arquivo" in resp.content.decode()


def test_tela_so_do_diretor(client, membro, um_aluno):
    montar = _montar(REPLICA.read_bytes())
    assert client.post(URL, montar("conferir")).status_code == 302
    client.force_login(membro)
    assert client.post(URL, montar("conferir")).status_code == 403


def test_modelo_para_download_e_importavel(cliente_diretor, diretor):
    ano = date.today().year
    resp = cliente_diretor.get(reverse("web:frequencia_modelo", args=["xlsx"]))
    grade = ler_grade(io.BytesIO(resp.content), "modelo.xlsx", ano=ano)
    assert [linha["matricula"] for linha in grade.linhas] == [
        f"S{ano % 100}0001",
        f"S{ano % 100}0002",
    ]
    assert set(grade.linhas[1]["codigos"].values()) == {"P", "F", "J", "S"}
    assert cliente_diretor.get(reverse("web:frequencia_modelo", args=["csv"])).status_code == 404
