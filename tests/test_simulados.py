"""Importação do relatório de simulado do P+ (RF004, RN003, RN004, RN006, RN009, RN010).

Só dados sintéticos (NF017): as réplicas `pequena/2026/planilhas/p_mais_simulado_*.xlsx` e
relatórios montados no mesmo layout por `ingestao.planilhas_casd`.
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
from openpyxl import load_workbook

from core.models import (
    Aluno,
    CicloCalendario,
    PendenciaImportacao,
    RegistroAlteracao,
    RegistroImportacao,
    ResultadoSimulado,
    Turma,
)
from ingestao import pendencias, planilhas_casd
from ingestao.cadastro import COLUNAS as COLUNAS_CADASTRO
from ingestao.cadastro import importar_cadastro
from ingestao.calendario import TIPOS
from ingestao.leitura import ArquivoInvalidoError, ler_tabela
from ingestao.simulados import aplicar_pendencia, importar_simulados, ler_relatorio
from tests.conftest import importar_em_dois_passos

pytestmark = pytest.mark.django_db

PASTA = Path(__file__).parent / "dados_sinteticos" / "pequena"
PLANILHAS = PASTA / "2026" / "planilhas"
PERFIS = {
    p["perfil"]: p for p in json.loads((PASTA / "perfis_conhecidos.json").read_text())["perfis"]
}
Area = ResultadoSimulado.Area
AREAS = ("HUMANAS", "LINGUAGENS", "NATUREZA", "MATEMATICA")


def _ler_csv(nome, colunas, opcionais=frozenset()):
    with (PASTA / "2026" / nome).open("rb") as f:
        return ler_tabela(f, nome, colunas=colunas, opcionais=opcionais)


def _aluno(matricula="S260001", notas=650.0, acertos=30, faltou=(), id_aluno=1, nome="Aluno Um"):
    return {
        "matricula": matricula,
        "nome": nome,
        "id_aluno": id_aluno,
        "inscricao": f"{id_aluno:07d}",
        "turma": "Turma 1",
        "notas": {a: None if a in faltou else notas for a in AREAS},
        "acertos": {a: None if a in faltou else acertos for a in AREAS},
    }


def _relatorio(*alunos, avaliacao="4º Simulado Enem"):
    conteudo = planilhas_casd.relatorio_pmais(avaliacao, 2026, list(alunos))
    return ler_relatorio(io.BytesIO(conteudo), "relatorio.xlsm")


def _replica(numero):
    caminho = PLANILHAS / f"p_mais_simulado_{numero:02d}.xlsx"
    return ler_relatorio(caminho.open("rb"), caminho.name)


def _ciclo_n(numero):
    return CicloCalendario.objects.filter(data_inicio__year=2026).order_by("data_inicio")[
        numero - 1
    ]


@pytest.fixture
def ano_2026(diretor):
    importar_cadastro(
        _ler_csv("cadastro_alunos.csv", COLUNAS_CADASTRO, frozenset({"data_ingresso"})),
        ano=2026,
        autor=diretor,
        data_mudanca=date(2026, 6, 25),
        gravar=True,
    )
    ciclos = TIPOS["ciclos"]
    ciclos.importar(
        _ler_csv("ciclos.csv", ciclos.colunas, ciclos.opcionais),
        ano=2026,
        autor=diretor,
        gravar=True,
    )


@pytest.fixture
def ciclo(db):
    return CicloCalendario.objects.create(
        data_inicio=date(2026, 3, 2), data_fim=date(2026, 3, 15), data_simulado=date(2026, 3, 15)
    )


@pytest.fixture
def aluno(ciclo):
    turma = Turma.objects.create(nome="Turma 1", ano=2026)
    return Aluno.objects.create(
        matricula="S260001", nome="Aluno Um", data_ingresso=date(2026, 2, 2), turma=turma
    )


def _importar(linhas, autor, ciclo, gravar=True):
    return importar_simulados(linhas, ano=2026, ciclo=ciclo, autor=autor, gravar=gravar)


# --- Réplicas dos relatórios ---------------------------------------------------------


@pytest.mark.regras
def test_replica_rn009_ausente_no_ciclo_6(diretor, ano_2026):
    linhas = _replica(6)
    resumo = _importar(linhas, diretor, _ciclo_n(6))
    assert resumo.total_linhas == len(linhas) == 20 and not resumo.inconsistentes
    ausente = PERFIS["ausente_no_simulado"]
    faltou = ResultadoSimulado.objects.filter(aluno_id=ausente["matricula"])
    assert faltou.count() == 4 and not faltou.filter(presente=True).exists()
    assert not faltou.exclude(nota_tri__isnull=True).exists() and resumo.ausentes >= 1
    assert ResultadoSimulado.objects.filter(acertos__isnull=False).exists()


@pytest.mark.regras
def test_replica_rn010_queda_entre_os_ciclos_7_e_8(diretor, ano_2026):
    queda = PERFIS["queda_de_desempenho"]
    for numero in (7, 8):
        _importar(_replica(numero), diretor, _ciclo_n(numero))
    notas = list(
        ResultadoSimulado.objects.filter(aluno_id=queda["matricula"], area=Area.MATEMATICA)
        .order_by("ciclo__data_inicio")
        .values_list("nota_tri", flat=True)
    )
    assert notas == [Decimal("650.0"), Decimal("590.0")]
    assert notas[1] - notas[0] == Decimal(str(queda["esperado"]["delta_tri"]))


def test_reimportar_a_replica_nao_duplica(diretor, ano_2026):
    _importar(_replica(6), diretor, _ciclo_n(6))
    segunda = _importar(_replica(6), diretor, _ciclo_n(6))
    assert segunda.sem_alteracao == 20 and segunda.importados == 0 and segunda.sobreposicoes
    assert ResultadoSimulado.objects.count() == 80


# --- Etapas, valores-limite e linhas inválidas (RN009, RN010) -----------------------------


@pytest.mark.regras
def test_falta_a_uma_etapa_so_tira_aquelas_areas(diretor, aluno, ciclo):
    resumo = _importar(_relatorio(_aluno(faltou=("HUMANAS", "LINGUAGENS"))), diretor, ciclo)
    assert resumo.ausencias_parciais == 1 and resumo.ausentes == 0
    presentes = dict(ResultadoSimulado.objects.values_list("area", "presente"))
    assert presentes == {
        "HUMANAS": False,
        "LINGUAGENS": False,
        "NATUREZA": True,
        "MATEMATICA": True,
    }
    assert ResultadoSimulado.objects.get(area="HUMANAS").nota_tri is None


@pytest.mark.regras
def test_valores_limite_aceitos(diretor, aluno, ciclo):
    linhas = _relatorio(_aluno(notas=1000.0, acertos=45))
    assert _importar(linhas, diretor, ciclo).criados == 1
    assert ResultadoSimulado.objects.get(area="NATUREZA").nota_tri == Decimal("1000.0")


@pytest.mark.regras
@pytest.mark.parametrize(
    "notas,acertos,motivo",
    [
        (650.0, 46, "acertos de CH fora de 0 a 45"),
        (1000.1, 30, "nota TRI de CH fora de 0 a 1000"),
        ("abc", 30, "nota TRI de CH fora de 0 a 1000"),
    ],
)
def test_valores_fora_do_limite(diretor, aluno, ciclo, notas, acertos, motivo):
    resumo = _importar(_relatorio(_aluno(notas=notas, acertos=acertos)), diretor, ciclo)
    assert [m for _, _, m in resumo.inconsistentes] == [motivo]
    assert not ResultadoSimulado.objects.exists()


def test_nota_sem_acertos_e_linha_sem_aba_de_acertos(diretor, aluno, ciclo):
    linhas = _relatorio(_aluno())
    linhas[0]["areas"]["MATEMATICA"] = (650.0, None)
    assert _importar(linhas, diretor, ciclo).inconsistentes[0][2] == (
        "nota e acertos de MT não batem (um deles em branco)"
    )
    linhas = _relatorio(_aluno())
    linhas[0]["tem_acertos"] = False
    assert "aba de acertos" in _importar(linhas, diretor, ciclo).inconsistentes[0][2]


def test_outra_avaliacao_repetido_e_fora_do_aluno(diretor, aluno, ciclo):
    turma = aluno.turma
    Aluno.objects.create(
        matricula="S260002", nome="Dois", data_ingresso=date(2026, 4, 1), turma=turma
    )
    linhas = _relatorio(
        _aluno(id_aluno=1),
        _aluno(id_aluno=2),
        _aluno("S260002", id_aluno=3),
        _aluno("S260003", id_aluno=4),
    )
    linhas[3]["avaliacao"] = "outra avaliacao"
    resumo = _importar(linhas, diretor, ciclo)
    assert [m for _, _, m in resumo.inconsistentes] == [
        "aluno repetido no relatório",
        "simulado antes do ingresso ou depois da saída do aluno (RN004)",
        "avaliação diferente do restante do arquivo",
    ]
    assert resumo.criados == 1 and resumo.total_linhas == 4


# --- Leitura do relatório ------------------------------------------------------------


def test_relatorio_sem_matricula_csv_e_sem_aba():
    conteudo = planilhas_casd.relatorio_pmais("Simulado", 2026, [_aluno()])
    livro = load_workbook(io.BytesIO(conteudo))
    livro[planilhas_casd.ABA_NOTAS_PMAIS].delete_cols(12)  # a coluna Matrícula
    saida = io.BytesIO()
    livro.save(saida)
    with pytest.raises(ArquivoInvalidoError, match="coluna Matrícula"):
        ler_relatorio(io.BytesIO(saida.getvalue()), "r.xlsx")
    with pytest.raises(ArquivoInvalidoError, match="duas abas"):
        ler_relatorio(io.BytesIO(b"a;b\n1;2\n"), "r.csv")
    del livro[planilhas_casd.ABA_ACERTOS_PMAIS]
    saida = io.BytesIO()
    livro.save(saida)
    with pytest.raises(ArquivoInvalidoError, match="não existe no arquivo"):
        ler_relatorio(io.BytesIO(saida.getvalue()), "r.xlsx")


def test_relatorio_sem_coluna_de_area():
    conteudo = planilhas_casd.relatorio_pmais("Simulado", 2026, [_aluno()])
    livro = load_workbook(io.BytesIO(conteudo))
    aba = livro[planilhas_casd.ABA_ACERTOS_PMAIS]
    for celula in aba[1]:
        if celula.value == "Matemática - Acertos":
            celula.value = "Matemática - Outra coisa"
    saida = io.BytesIO()
    livro.save(saida)
    with pytest.raises(ArquivoInvalidoError, match="Matemática - Acertos"):
        ler_relatorio(io.BytesIO(saida.getvalue()), "r.xlsx")


# --- Reimportação com auditoria (NF008, NF009) ---------------------------------------


def test_reimportar_atualiza_com_auditoria(diretor, aluno, ciclo):
    _importar(_relatorio(_aluno()), diretor, ciclo)
    novo = _relatorio(_aluno(notas=660.5, acertos=31))
    conferencia = _importar(novo, diretor, ciclo, gravar=False)
    assert conferencia.atualizados == 1 and conferencia.sobreposicoes
    _importar(novo, diretor, ciclo)
    lc = ResultadoSimulado.objects.get(area=Area.LINGUAGENS)
    assert lc.acertos == 31 and lc.nota_tri == Decimal("660.5")
    campos = set(
        RegistroAlteracao.objects.filter(objeto_id=str(lc.pk)).values_list("campo", flat=True)
    )
    assert campos == {"acertos", "nota_tri"}


# --- Pendências (RN003) --------------------------------------------------------------


def test_pendencia_associada_vale_na_reimportacao(diretor, aluno, ciclo):
    linhas = _relatorio(_aluno(matricula=""))
    assert _importar(linhas, diretor, ciclo).pendencias == [(2, "Matrícula em branco")]
    pendencia = PendenciaImportacao.objects.get()
    assert pendencia.origem == "SIMULADO" and pendencia.dados["ciclo"] == ciclo.pk
    assert pendencias.associar([pendencia], aluno, autor=diretor) == (1, [])
    assert ResultadoSimulado.objects.filter(aluno=aluno).count() == 4
    # o P+ corrigiu as notas: a reimportação, ainda sem matrícula, atualiza o aluno associado
    resumo = _importar(_relatorio(_aluno(matricula="", notas=700.0)), diretor, ciclo)
    assert resumo.pendencias == [] and resumo.atualizados == 1
    assert ResultadoSimulado.objects.get(area="MATEMATICA").nota_tri == Decimal("700.0")
    assert aplicar_pendencia(pendencia, aluno, diretor) == "o aluno já tem resultado neste simulado"


def test_pendencia_descartada_e_ignorada(diretor, aluno, ciclo):
    _importar(_relatorio(_aluno(matricula="")), diretor, ciclo)
    pendencias.descartar(list(PendenciaImportacao.objects.all()), autor=diretor)
    resumo = _importar(_relatorio(_aluno(matricula="")), diretor, ciclo)
    assert resumo.pendencias == [] and resumo.sem_alteracao == 1


def test_aplicador_recusa_ciclo_inexistente_e_fora_do_aluno(diretor, aluno, ciclo):
    sem_ciclo = PendenciaImportacao(dados={"ciclo": 999, "areas": {}})
    assert aplicar_pendencia(sem_ciclo, aluno, diretor) == "o ciclo do simulado não existe mais"
    aluno.corrigir_ingresso(date(2026, 3, 20))
    antes = PendenciaImportacao(dados={"ciclo": ciclo.pk, "areas": {}})
    assert "antes do ingresso" in aplicar_pendencia(antes, aluno, diretor)


# --- Datas do ciclo são fixas depois dos resultados ----------------------------------


def test_ciclo_com_resultados_nao_muda_de_data(diretor, aluno, ciclo):
    ciclo.data_fim = date(2026, 3, 16)
    ciclo.full_clean()  # sem resultados: pode
    ciclo.data_fim = date(2026, 3, 15)
    _importar(_relatorio(_aluno()), diretor, ciclo)
    ciclo.data_simulado = date(2026, 3, 14)
    with pytest.raises(ValidationError, match="datas do ciclo são fixas"):
        ciclo.full_clean()
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
    _importar(_relatorio(_aluno()), diretor, ciclo)
    url = reverse("web:calendario_item", args=["ciclos", ciclo.pk])
    resp = cliente_diretor.post(
        url, {"data_inicio": "2026-03-02", "data_fim": "2026-03-16", "data_simulado": "2026-03-15"}
    )
    assert resp.status_code == 200 and "datas do ciclo são fixas" in resp.content.decode()


# --- Tela (RN013) --------------------------------------------------------------------

URL = reverse("web:simulados_importar")


def _montar(conteudo, ciclo, ano=2026):
    def montar(acao):
        arquivo = SimpleUploadedFile("Exemplo de Planilha de Notas.xlsm", conteudo)
        return {"arquivo": arquivo, "ano": ano, "ciclo": ciclo.pk, "acao": acao}

    return montar


def test_tela_confere_e_confirma_a_replica(cliente_diretor, diretor, ano_2026):
    montar = _montar((PLANILHAS / "p_mais_simulado_06.xlsx").read_bytes(), _ciclo_n(6))
    conferencia = cliente_diretor.post(URL, montar("conferir"))
    assert "Ausentes no simulado (RN009): 1" in conferencia.content.decode()
    assert not ResultadoSimulado.objects.exists()
    resp = importar_em_dois_passos(cliente_diretor, URL, montar)
    assert resp.context["resultado"].gravado and ResultadoSimulado.objects.count() == 80
    assert RegistroImportacao.objects.get().tipo == RegistroImportacao.Tipo.SIMULADOS


def test_tela_recusa_ciclo_de_outro_ano(cliente_diretor, aluno, ciclo):
    conteudo = planilhas_casd.relatorio_pmais("S", 2026, [_aluno()])
    resp = cliente_diretor.post(URL, _montar(conteudo, ciclo, ano=2027)("conferir"))
    assert "precisa ser do ano letivo" in resp.content.decode()


def test_tela_so_do_diretor(client, membro, aluno, ciclo):
    montar = _montar(planilhas_casd.relatorio_pmais("S", 2026, [_aluno()]), ciclo)
    assert client.post(URL, montar("conferir")).status_code == 302
    client.force_login(membro)
    assert client.post(URL, montar("conferir")).status_code == 403


def test_modelo_para_download_e_importavel(cliente_diretor, diretor):
    ano = date.today().year
    resp = cliente_diretor.get(reverse("web:simulados_modelo", args=["xlsx"]))
    linhas = ler_relatorio(io.BytesIO(resp.content), "modelo.xlsx")
    turma = Turma.objects.create(nome="Turma 1", ano=ano)
    for n in (1, 2):
        Aluno.objects.create(
            matricula=f"S{ano % 100}000{n}", nome="X", data_ingresso=date(ano, 1, 1), turma=turma
        )
    ciclo = CicloCalendario.objects.create(
        data_inicio=date(ano, 3, 2), data_fim=date(ano, 3, 15), data_simulado=date(ano, 3, 15)
    )
    resumo = importar_simulados(linhas, ano=ano, ciclo=ciclo, autor=diretor, gravar=True)
    assert resumo.criados == 2 and resumo.ausencias_parciais == 1
    assert cliente_diretor.get(reverse("web:simulados_modelo", args=["csv"])).status_code == 404
