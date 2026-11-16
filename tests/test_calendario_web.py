"""Telas do calendário letivo (RF007): leitura, importação e modelos."""

import io
from datetime import date

import pytest
from django.urls import reverse

from core.models import CicloCalendario, DiaCalendario, RegistroImportacao, TemaRedacao
from ingestao.calendario import TIPOS
from ingestao.leitura import ler_tabela
from tests.conftest import SENHA

pytestmark = pytest.mark.django_db

ESCRITA = [
    ("web:calendario_importar", {}),
]


@pytest.mark.parametrize(("nome", "kw"), ESCRITA)
@pytest.mark.parametrize("metodo", ["get", "post"])
def test_anonimo_vai_ao_login(client, nome, kw, metodo):
    r = getattr(client, metodo)(reverse(nome, kwargs=kw))
    assert r.status_code == 302 and "/entrar/" in r["Location"]


@pytest.mark.parametrize(("nome", "kw"), ESCRITA)
@pytest.mark.parametrize("metodo", ["get", "post"])
def test_membro_nao_escreve(client, membro, nome, kw, metodo):
    client.force_login(membro)
    assert getattr(client, metodo)(reverse(nome, kwargs=kw)).status_code == 403


def test_membro_le_calendario(client, membro):
    DiaCalendario.objects.create(data=date(2026, 2, 16), letivo=False, descricao="Carnaval")
    CicloCalendario.objects.create(data_inicio=date(2026, 2, 2), data_fim=date(2026, 2, 15))
    TemaRedacao.objects.create(data=date(2026, 2, 3), tema="Tema <b>x</b>")
    client.force_login(membro)
    r = client.get(reverse("web:calendario"))
    assert r.status_code == 200
    conteudo = r.content.decode()
    assert "Carnaval" in conteudo and "Tema &lt;b&gt;x&lt;/b&gt;" in conteudo
    assert "Importar planilha" not in conteudo


def test_calendario_vazio(client, membro):
    client.force_login(membro)
    assert client.get(reverse("web:calendario")).status_code == 200


def _csv(conteudo, nome="t.csv"):
    arq = io.BytesIO(conteudo.encode("utf-8"))
    arq.name = nome
    return arq


def _enviar(cliente, tipo, arquivo, acao, ano=2026):
    return cliente.post(
        reverse("web:calendario_importar"),
        {"tipo": tipo, "arquivo": arquivo, "ano": ano, "acao": acao},
    )


def test_importar_conferir_nao_grava(cliente_diretor):
    r = _enviar(cliente_diretor, "dias", _csv("data;dia_letivo\n16/02/2026;N\n"), "conferir")
    assert r.status_code == 200 and r.context["resumo"].criados == 1
    assert DiaCalendario.objects.count() == 0 and RegistroImportacao.objects.count() == 0


def test_importar_grava_e_registra_trilha(cliente_diretor, diretor):
    _enviar(cliente_diretor, "dias", _csv("data;dia_letivo\n16/02/2026;S\n"), "importar")
    _enviar(cliente_diretor, "dias", _csv("data;dia_letivo\n16/02/2026;N\n"), "importar")
    primeiro, segundo = RegistroImportacao.objects.order_by("id")
    assert primeiro.tipo == "CALENDARIO" and primeiro.criados == 1
    assert (segundo.atualizados, segundo.criados, segundo.autor) == (1, 0, diretor)
    assert segundo.nome_arquivo == "t.csv"


def test_importar_arquivo_invalido_vira_erro_de_formulario(cliente_diretor):
    r = _enviar(cliente_diretor, "dias", _csv("x;y\n1;2\n"), "importar")
    assert r.status_code == 200 and r.context["form"].errors["arquivo"]
    r = _enviar(cliente_diretor, "dias", _csv("a", "t.txt"), "importar")
    assert r.status_code == 200 and r.context["form"].errors["arquivo"]


@pytest.mark.parametrize("tipo", list(TIPOS))
@pytest.mark.parametrize("formato", ["csv", "xlsx"])
def test_modelo_baixado_importa_sem_inconsistencia(client, membro, tipo, formato):
    client.force_login(membro)
    r = client.get(reverse("web:calendario_modelo", args=[tipo, formato]))
    assert r.status_code == 200 and "attachment" in r["Content-Disposition"]
    t = TIPOS[tipo]
    arq = io.BytesIO(r.content)
    linhas = ler_tabela(arq, f"m.{formato}", colunas=t.colunas, opcionais=t.opcionais)
    diretor = membro.__class__.objects.create_user("d2", "d2@x.org", SENHA, perfil="DIRETOR")
    resumo = t.importar(linhas, ano=2026, autor=diretor, gravar=False)
    assert resumo.inconsistentes == [] and resumo.criados == len(linhas)


@pytest.mark.parametrize(("tipo", "formato"), [("xx", "csv"), ("dias", "pdf")])
def test_modelo_desconhecido_404(client, membro, tipo, formato):
    client.force_login(membro)
    assert client.get(reverse("web:calendario_modelo", args=[tipo, formato])).status_code == 404
