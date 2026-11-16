"""Fluxo web das importações: conferência obrigatória e confirmação com token (NF006, NF008,
NF011). Cobre o cadastro e o calendário."""

import io
import time
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import Aluno, DiaCalendario, RegistroImportacao, Turma
from tests.conftest import importar_em_dois_passos

pytestmark = pytest.mark.django_db

PEQUENA = Path(__file__).parent / "dados_sinteticos" / "pequena" / "2026" / "cadastro_alunos.csv"
DIAS = "data;dia_letivo\n16/02/2026;N\n17/02/2026;S\n"

URL_CAD = "web:cadastro_importar"
URL_CAL = "web:calendario_importar"


def _cad(conteudo=None, ano=2026):
    dados = PEQUENA.read_bytes() if conteudo is None else conteudo

    def montar(acao):
        return {
            "arquivo": SimpleUploadedFile("cad.csv", dados),
            "ano": ano,
            "data_mudanca": "2026-03-02",
            "acao": acao,
        }

    return montar


def _cal(conteudo=DIAS, ano=2026):
    def montar(acao):
        arq = io.BytesIO(conteudo.encode())
        arq.name = "t.csv"
        return {"tipo": "dias", "arquivo": arq, "ano": ano, "acao": acao}

    return montar


CASOS = {
    "cadastro": (URL_CAD, _cad, lambda: Aluno.objects.count(), 20),
    "calendario": (URL_CAL, _cal, lambda: DiaCalendario.objects.count(), 2),
}


@pytest.fixture(params=list(CASOS))
def caso(request):
    url, fabrica, contar, esperado = CASOS[request.param]
    montar = fabrica()
    return reverse(url), montar, contar, esperado


def test_importar_sem_token_so_confere(cliente_diretor, caso):
    url, montar, contar, _ = caso
    resp = cliente_diretor.post(url, montar("importar"))
    resultado = resp.context["resultado"]
    assert not resultado.gravado and resultado.token and not resultado.aviso
    assert contar() == 0 and not RegistroImportacao.objects.exists()
    assert "Confirmar importação" in resp.content.decode()


def test_conferir_e_confirmar_grava_e_registra_trilha(cliente_diretor, diretor, caso):
    url, montar, contar, esperado = caso
    assert cliente_diretor.post(url, montar("conferir")).context["resultado"].token
    assert contar() == 0
    resp = importar_em_dois_passos(cliente_diretor, url, montar)
    assert resp.context["resultado"].gravado and "Importação concluída" in resp.content.decode()
    assert contar() == esperado
    assert RegistroImportacao.objects.get().autor == diretor


def test_confirmar_com_outro_arquivo_vira_conferencia_com_aviso(cliente_diretor, caso):
    url, montar, contar, _ = caso
    token = cliente_diretor.post(url, montar("conferir")).context["resultado"].token
    outro = _cad(PEQUENA.read_bytes() + b"\n") if url == reverse(URL_CAD) else _cal(DIAS + "\n")
    resp = cliente_diretor.post(url, {**outro("importar"), "token": token})
    resultado = resp.context["resultado"]
    assert not resultado.gravado and resultado.aviso and resultado.token != token
    assert contar() == 0 and not RegistroImportacao.objects.exists()


def test_confirmar_com_parametro_diferente_vira_conferencia(cliente_diretor):
    url = reverse(URL_CAD)
    token = cliente_diretor.post(url, _cad()("conferir")).context["resultado"].token
    montar = _cad()("importar")
    montar["data_mudanca"] = "2026-04-06"
    resp = cliente_diretor.post(url, {**montar, "token": token})
    assert not resp.context["resultado"].gravado and Aluno.objects.count() == 0


def test_confirmar_apos_mudanca_no_banco_vira_conferencia(cliente_diretor):
    url = reverse(URL_CAD)
    token = cliente_diretor.post(url, _cad()("conferir")).context["resultado"].token
    turma = Turma.objects.create(nome="Turma A", ano=2026)
    Aluno.objects.create(  # aluno do arquivo criado entre os dois passos
        matricula="S260001", nome="Qualquer", data_ingresso="2026-02-02", turma=turma
    )
    antes = Aluno.objects.count()
    resp = cliente_diretor.post(url, {**_cad()("importar"), "token": token})
    assert not resp.context["resultado"].gravado and resp.context["resultado"].aviso
    assert Aluno.objects.count() == antes and not RegistroImportacao.objects.exists()


def test_reconfirmar_mesmo_token_nao_duplica(cliente_diretor, caso):
    url, montar, contar, esperado = caso
    token = cliente_diretor.post(url, montar("conferir")).context["resultado"].token
    cliente_diretor.post(url, {**montar("importar"), "token": token})
    segunda = cliente_diretor.post(url, {**montar("importar"), "token": token})
    assert contar() == esperado  # NF008: nada duplicado
    # o resumo mudou (agora tudo é "sem alteração"): vira conferência, não grava de novo
    assert not segunda.context["resultado"].gravado
    assert RegistroImportacao.objects.count() == 1


def test_resumo_mostra_importados_ignorados_inconsistentes(cliente_diretor):
    url = reverse(URL_CAL)
    conteudo = "data;dia_letivo\n16/02/2026;N\n16/02/2026;S\nxx;S\n"
    resp = cliente_diretor.post(url, _cal(conteudo)("conferir"))
    html = resp.content.decode()
    assert "Importados: 1" in html and "Ignorados (sem alteração): 0" in html
    assert "Inconsistentes (linhas recusadas): 2" in html
    assert "Total de linhas do arquivo: 3" in html


def test_membro_403_e_anonimo_login(client, membro, caso):
    url, montar, contar, _ = caso
    resp = client.post(url, montar("conferir"))
    assert resp.status_code == 302 and "/entrar/" in resp["Location"]
    client.force_login(membro)
    assert client.post(url, montar("conferir")).status_code == 403
    assert contar() == 0


def test_importa_500_alunos_em_menos_de_2_minutos(cliente_diretor):
    """NF011: conferir e confirmar 500 alunos, pelo cliente web, em menos de 2 minutos."""
    linhas = ["matricula;nome;turma;data_ingresso"]
    for i in range(1, 501):
        linhas.append(f"S26{i:04d};Aluno Sintético {i};Turma {i % 5 + 1};02/02/2026")
    conteudo = "\n".join(linhas).encode()
    inicio = time.perf_counter()
    resp = importar_em_dois_passos(cliente_diretor, reverse(URL_CAD), _cad(conteudo))
    duracao = time.perf_counter() - inicio
    assert resp.context["resultado"].gravado
    assert Aluno.objects.count() == 500 and Turma.objects.count() == 5
    assert duracao < 120
