"""Importação da exportação do Corrija-me (RF005, RN003, RN004, RN007, NF006, NF008, NF009).

Só dados sintéticos (NF017): as réplicas `pequena/2026/planilhas/corrija_me_*.xlsx` e
exportações montadas no mesmo layout por `ingestao.planilhas_casd`.
"""

import io
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
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
from ingestao import pendencias, planilhas_casd
from ingestao.cadastro import COLUNAS as COLUNAS_CADASTRO
from ingestao.cadastro import importar_cadastro
from ingestao.leitura import ler_tabela
from ingestao.redacoes import COLUNAS, OPCIONAIS, aplicar_pendencia, importar_redacoes
from tests.conftest import importar_em_dois_passos

pytestmark = pytest.mark.django_db

PASTA = Path(__file__).parent / "dados_sinteticos" / "pequena"
PLANILHAS = PASTA / "2026" / "planilhas"
CONHECIDOS = json.loads((PASTA / "perfis_conhecidos.json").read_text())
TERCA = date(2026, 3, 3)
ENVIO = datetime(2026, 3, 5, 18, 0)


def _ler_csv(nome, colunas, opcionais=frozenset()):
    with (PASTA / "2026" / nome).open("rb") as f:
        return ler_tabela(f, nome, colunas=colunas, opcionais=opcionais)


def _redacao(rm="S260001", notas=(160, 160, 160, 160, 160), final=800, banca="ENEM", **extra):
    return {
        "id": extra.get("id", 1),
        "atividade": extra.get("atividade", 7001),
        "envio": extra.get("envio", ENVIO),
        "correcao": ENVIO + timedelta(days=2),
        "nome": extra.get("nome", "Aluno Sintético Um"),
        "rm": rm,
        "banca": banca,
        "tema": extra.get("tema", "Tema A"),
        "notas": list(notas),
        "final": final,
        "turma": "CASDvest 2026 - Turma 1",
    }


def _exportacao(*redacoes):
    conteudo = planilhas_casd.exportacao_corrija_me(list(redacoes))
    return ler_tabela(io.BytesIO(conteudo), "corrija.xlsx", colunas=COLUNAS, opcionais=OPCIONAIS)


def _importar(linhas, autor, terca=TERCA, gravar=True):
    return importar_redacoes(linhas, ano=2026, terca=terca, autor=autor, gravar=gravar)


@pytest.fixture
def ano_2026(diretor):
    importar_cadastro(
        _ler_csv("cadastro_alunos.csv", COLUNAS_CADASTRO, frozenset({"data_ingresso"})),
        ano=2026,
        autor=diretor,
        data_mudanca=date(2026, 6, 25),
        gravar=True,
    )


@pytest.fixture
def aluno(db):
    turma = Turma.objects.create(nome="Turma 1", ano=2026)
    return Aluno.objects.create(
        matricula="S260001", nome="Aluno Sintético Um", data_ingresso=date(2026, 2, 2), turma=turma
    )


# --- Réplica da exportação -----------------------------------------------------------


def test_replica_com_matricula_em_branco(diretor, ano_2026):
    em_branco = next(i for i in CONHECIDOS["inconsistencias"] if i["tipo"] == "matricula_em_branco")
    terca = date(2026, 2, 24)
    caminho = PLANILHAS / "corrija_me_2026-02-24.xlsx"
    linhas = ler_tabela(caminho.open("rb"), caminho.name, colunas=COLUNAS, opcionais=OPCIONAIS)
    resumo = _importar(linhas, diretor, terca)
    assert resumo.total_linhas == len(linhas) and not resumo.inconsistentes
    # RN007: o tema da terça é criado com o título do arquivo
    assert (
        resumo.temas_criados == 1 and TemaRedacao.objects.get(data=terca).tema == linhas[0]["tema"]
    )
    # RN003: a redação sem RM vira pendência; o nome é só verificação
    pendencia = PendenciaImportacao.objects.get()
    assert pendencia.motivo == "EM_BRANCO" and pendencia.nome_informado == em_branco["nome"]
    # quem não aparece no arquivo (só entregas) fica como não entregue
    entregues = ResultadoRedacao.objects.filter(tema_semana=terca, entregue=True).count()
    assert entregues == len(linhas) - 1 == resumo.criados
    no_curso = Aluno.objects.filter(data_ingresso__lte=terca + timedelta(days=6)).count()
    assert no_curso < 20  # RN004: quem ingressa nas chamadas seguintes não conta
    assert resumo.nao_entregues == no_curso - entregues
    nao = ResultadoRedacao.objects.filter(tema_semana=terca, entregue=False)
    assert nao.count() == resumo.nao_entregues and not nao.exclude(nota_c1__isnull=True).exists()
    # na base sintética, a dona do nome só ingressa depois deste tema: associar é recusado (RN004)
    orfa = Aluno.objects.get(nome=em_branco["nome"])
    assert orfa.data_ingresso > terca + timedelta(days=6)
    associadas, recusas = pendencias.associar([pendencia], orfa, autor=diretor)
    assert associadas == 0 and "antes do ingresso" in recusas[0][1]
    # associar a um aluno que estava no curso corrige o "não entregue" dele
    outro = nao.first().aluno
    assert pendencias.associar([pendencia], outro, autor=diretor, confirmar_nome=True) == (1, [])
    redacao = ResultadoRedacao.objects.get(aluno=outro, tema_semana=terca)
    assert redacao.entregue and redacao.nota_total == 600
    assert RegistroAlteracao.objects.filter(objeto_id=str(redacao.pk), campo="entregue").exists()


def test_reimportar_a_replica_nao_duplica(diretor, ano_2026):
    caminho = PLANILHAS / "corrija_me_2026-02-03.xlsx"
    linhas = ler_tabela(caminho.open("rb"), caminho.name, colunas=COLUNAS, opcionais=OPCIONAIS)
    primeira = _importar(linhas, diretor, date(2026, 2, 3))
    segunda = _importar(linhas, diretor, date(2026, 2, 3))
    assert segunda.importados == 0 and segunda.nao_entregues == 0 and segunda.temas_criados == 0
    assert segunda.sem_alteracao == primeira.criados and segunda.sobreposicoes
    no_curso = Aluno.objects.filter(data_ingresso__lte=date(2026, 2, 9)).count()
    assert ResultadoRedacao.objects.count() == no_curso


# --- Bancas e valores-limite ---------------------------------------------------------


def test_enem_valores_limite(diretor, aluno):
    resumo = _importar(_exportacao(_redacao(notas=(0, 200, 0, 200, 0), final=400)), diretor)
    assert resumo.criados == 1
    redacao = ResultadoRedacao.objects.get()
    assert redacao.entregue and redacao.banca == "ENEM" and redacao.nota_total == 400
    assert redacao.tema == "Tema A" and redacao.tema_semana == TERCA


def test_vunesp_aceita_decimais_e_quatro_criterios(diretor, aluno):
    linhas = _exportacao(
        _redacao(notas=(21.4, 21.4, 21.4, 14.3, None), final=78.58, banca="VUNESP - CONCURSOS")
    )
    assert _importar(linhas, diretor).criados == 1
    redacao = ResultadoRedacao.objects.get()
    assert redacao.nota_c1 == Decimal("21.4") and redacao.nota_c5 is None
    assert redacao.nota_final == Decimal("78.58") and redacao.nota_total == Decimal("78.58")


@pytest.mark.parametrize(
    "notas,final,banca,motivo",
    [
        ((160, 160, 160, 160, None), 640, "ENEM", "competência 5 em branco"),
        ((201, 160, 160, 160, 160), 841, "ENEM", "competência 1 fora de 0 a 200"),
        ((160, -1, 160, 160, 160), 639, "ENEM", "competência 2 fora de 0 a 200"),
        ((160, 160, 160, 160, 160), 801, "ENEM", "nota final diferente da soma das competências"),
        ((21.4, 21.4, None, 14.3, None), 50, "VUNESP", "competência 3 em branco"),
        ((21.4, 21.4, 21.4, 14.3, None), 1000.5, "VUNESP", "nota final fora de 0 a 1000"),
    ],
)
def test_linhas_invalidas(diretor, aluno, notas, final, banca, motivo):
    resumo = _importar(_exportacao(_redacao(notas=notas, final=final, banca=banca)), diretor)
    assert [m for _, _, m in resumo.inconsistentes] == [motivo]
    assert not ResultadoRedacao.objects.filter(entregue=True).exists()


def test_banca_em_branco_e_enem_e_nota_final_opcional(diretor, aluno):
    assert _importar(_exportacao(_redacao(final=None, banca="")), diretor).criados == 1
    assert ResultadoRedacao.objects.get().nota_total == 800


# --- Tema, atividade, reenvio e janela do aluno --------------------------------------


def test_tema_cadastrado_e_mantido_e_avisa(diretor, aluno):
    TemaRedacao.objects.create(data=TERCA, tema="Tema cadastrado")
    resumo = _importar(_exportacao(_redacao(tema="OUTRO TÍTULO")), diretor)
    assert resumo.temas_criados == 0
    assert [m for _, m in resumo.avisos] == [
        "03/03/2026: o tema do arquivo difere do cadastrado; mantido o cadastrado"
    ]
    assert ResultadoRedacao.objects.get().tema == "Tema cadastrado"
    assert not _importar(_exportacao(_redacao(tema="tema cadastrádo")), diretor).avisos


def test_sem_tema_cadastrado_nem_titulo_tudo_e_inconsistente(diretor, aluno):
    resumo = _importar(_exportacao(_redacao(tema="")), diretor)
    assert resumo.inconsistentes[0][2] == "tema não cadastrado nesta terça e sem título no arquivo"
    assert not ResultadoRedacao.objects.exists() and not TemaRedacao.objects.exists()


def test_reenvio_vale_o_mais_recente(diretor, aluno):
    antiga = _redacao(id=1, notas=(120,) * 5, final=600, envio=ENVIO)
    nova = _redacao(id=2, notas=(160,) * 5, final=800, envio=ENVIO + timedelta(hours=3))
    resumo = _importar(_exportacao(antiga, nova), diretor)
    assert resumo.criados == 1 and resumo.reenvios == 1 and resumo.total_linhas == 2
    assert ResultadoRedacao.objects.get().nota_total == 800


def test_outra_atividade_e_fora_do_aluno(diretor, aluno):
    Aluno.objects.create(
        matricula="S260002", nome="Dois", data_ingresso=date(2026, 3, 10), turma=aluno.turma
    )
    resumo = _importar(
        _exportacao(
            _redacao(id=1),
            _redacao(id=2, rm="S260002"),
            _redacao(id=3, rm="S260003"),
            _redacao(id=4, rm="S260001", atividade=9999, envio=ENVIO + timedelta(days=1)),
        ),
        diretor,
    )
    motivos = sorted(m for _, _, m in resumo.inconsistentes)
    assert motivos == [
        "redação de outra atividade do Corrija-me (ID DA ATIVIDADE)",
        "tema de antes do ingresso ou depois da saída do aluno (RN004)",
    ]
    assert resumo.criados == 1 and len(resumo.pendencias) == 1  # S260003 não existe


def test_ingresso_no_meio_da_semana_do_tema_conta(diretor, aluno):
    aluno.corrigir_ingresso(date(2026, 3, 9))  # a segunda que fecha a semana do tema
    assert _importar(_exportacao(_redacao()), diretor).criados == 1


# --- Não entregue --------------------------------------------------------------------


def test_nao_entregue_respeita_janela_e_registro_existente(diretor, aluno):
    turma = aluno.turma
    Aluno.objects.create(
        matricula="S260002", nome="Dois", data_ingresso=date(2026, 2, 2), turma=turma
    )
    Aluno.objects.create(
        matricula="S260003", nome="Três", data_ingresso=date(2026, 4, 1), turma=turma
    )
    Aluno.objects.create(
        matricula="S260004",
        nome="Quatro",
        data_ingresso=date(2026, 2, 2),
        turma=turma,
        situacao=Aluno.Situacao.INVALIDO,
    )
    TemaRedacao.objects.create(data=TERCA, tema="Tema A")
    ResultadoRedacao.objects.create(
        aluno_id="S260001", tema_semana=TERCA, tema="Tema A", entregue=True, nota_final=800
    )
    resumo = _importar(_exportacao(_redacao(rm="S269999")), diretor)
    assert resumo.nao_entregues == 1  # só S260002: S260003 ainda não ingressou; S260004 é inválido
    assert ResultadoRedacao.objects.get(aluno_id="S260002").entregue is False
    assert ResultadoRedacao.objects.get(aluno_id="S260001").entregue is True  # não é tocado


# --- Reimportação com auditoria (NF008, NF009) ---------------------------------------


def test_reimportar_atualiza_com_auditoria(diretor, aluno):
    _importar(_exportacao(_redacao()), diretor)
    novo = _exportacao(_redacao(notas=(200, 160, 160, 160, 160), final=840))
    conferencia = _importar(novo, diretor, gravar=False)
    assert conferencia.atualizados == 1 and conferencia.sobreposicoes
    assert ResultadoRedacao.objects.get().nota_c1 == 160
    _importar(novo, diretor)
    redacao = ResultadoRedacao.objects.get()
    assert redacao.nota_c1 == 200
    campos = set(
        RegistroAlteracao.objects.filter(
            modelo="core.resultadoredacao", objeto_id=str(redacao.pk)
        ).values_list("campo", flat=True)
    )
    assert campos == {"nota_c1", "nota_final"}


# --- Pendências (RN003) --------------------------------------------------------------


def test_pendencia_associada_vale_na_reimportacao(diretor, aluno):
    assert _importar(_exportacao(_redacao(rm="")), diretor).pendencias == [
        (2, "Matrícula em branco")
    ]
    pendencia = PendenciaImportacao.objects.get()
    assert pendencias.associar([pendencia], aluno, autor=diretor) == (1, [])
    resumo = _importar(
        _exportacao(_redacao(rm="", notas=(200, 160, 160, 160, 160), final=840)), diretor
    )
    assert resumo.pendencias == [] and resumo.atualizados == 1
    assert ResultadoRedacao.objects.get().nota_total == 840
    assert (
        aplicar_pendencia(pendencia, aluno, diretor) == "o aluno já tem redação entregue neste tema"
    )


def test_pendencia_descartada_e_ignorada(diretor, aluno):
    _importar(_exportacao(_redacao(rm="", nome="Desconhecido")), diretor)
    pendencias.descartar(list(PendenciaImportacao.objects.all()), autor=diretor)
    resumo = _importar(_exportacao(_redacao(rm="", nome="Desconhecido")), diretor)
    assert resumo.pendencias == [] and resumo.sem_alteracao == 1


def test_aplicador_recusa_tema_ausente_e_fora_do_aluno(diretor, aluno):
    dados = {"tema_semana": "2026-03-10", "valores": {}}
    assert (
        aplicar_pendencia(PendenciaImportacao(dados=dados), aluno, diretor)
        == "o tema da redação não está cadastrado"
    )
    TemaRedacao.objects.create(data=date(2026, 1, 6), tema="Tema antigo")
    antes = {"tema_semana": "2026-01-06", "valores": {}}
    assert "antes do ingresso" in aplicar_pendencia(
        PendenciaImportacao(dados=antes), aluno, diretor
    )


# --- Tela (RN013) --------------------------------------------------------------------

URL = reverse("web:redacoes_importar")


def _montar(conteudo, terca="2026-03-03", ano=2026):
    def montar(acao):
        arquivo = SimpleUploadedFile("Exemplo_Planilha_Corrijame.xlsx", conteudo)
        return {"arquivo": arquivo, "ano": ano, "terca": terca, "acao": acao}

    return montar


def test_tela_confere_e_confirma(cliente_diretor, diretor, aluno):
    conteudo = planilhas_casd.exportacao_corrija_me(
        [_redacao(), _redacao(id=2, rm="", nome="Sem RM")]
    )
    montar = _montar(conteudo)
    conferencia = cliente_diretor.post(URL, montar("conferir"))
    html = conferencia.content.decode()
    assert (
        "Pendências para associação manual: 1" in html
        and "Tema criado a partir do arquivo: sim" in html
    )
    assert not ResultadoRedacao.objects.exists() and not TemaRedacao.objects.exists()
    resp = importar_em_dois_passos(cliente_diretor, URL, montar)
    assert resp.context["resultado"].gravado and ResultadoRedacao.objects.count() == 1
    trilha = RegistroImportacao.objects.get()
    assert trilha.tipo == RegistroImportacao.Tipo.REDACOES and trilha.pendencias == 1


def test_tela_valida_a_terca(cliente_diretor, aluno):
    conteudo = planilhas_casd.exportacao_corrija_me([_redacao()])
    resp = cliente_diretor.post(URL, _montar(conteudo, terca="2026-03-04")("conferir"))
    assert "terça-feira" in resp.content.decode()
    resp = cliente_diretor.post(URL, _montar(conteudo, terca="2027-03-02", ano=2026)("conferir"))
    assert "precisa ser do ano letivo" in resp.content.decode()


def test_tela_so_do_diretor(client, membro, aluno):
    montar = _montar(planilhas_casd.exportacao_corrija_me([_redacao()]))
    assert client.post(URL, montar("conferir")).status_code == 302
    client.force_login(membro)
    assert client.post(URL, montar("conferir")).status_code == 403


def test_modelo_para_download_e_importavel(cliente_diretor, diretor):
    ano = date.today().year
    resp = cliente_diretor.get(reverse("web:redacoes_modelo", args=["xlsx"]))
    linhas = ler_tabela(io.BytesIO(resp.content), "m.xlsx", colunas=COLUNAS, opcionais=OPCIONAIS)
    turma = Turma.objects.create(nome="Turma 1", ano=ano)
    for n in (1, 2):
        Aluno.objects.create(
            matricula=f"S{ano % 100}000{n}", nome="X", data_ingresso=date(ano, 1, 1), turma=turma
        )
    terca = date(ano, 3, 3) + timedelta(days=(1 - date(ano, 3, 3).weekday()) % 7)
    resumo = importar_redacoes(linhas, ano=ano, terca=terca, autor=diretor, gravar=True)
    assert resumo.criados == 2 and not resumo.inconsistentes
    assert cliente_diretor.get(reverse("web:redacoes_modelo", args=["csv"])).status_code == 404
