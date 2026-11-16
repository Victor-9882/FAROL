"""Modelos de planilha para download (RF006; reutilizados por RF003 a RF005)."""

import io

import pytest
from django.urls import reverse

from core.models import Aluno
from ingestao.cadastro import COLUNAS, EXEMPLOS, importar_cadastro
from ingestao.leitura import ler_tabela
from ingestao.modelos import gerar_modelo_csv, gerar_modelo_xlsx

pytestmark = pytest.mark.django_db
FORMATOS = ["xlsx", "csv"]


def _baixar(client, formato):
    return client.get(reverse(f"web:cadastro_modelo_{formato}"))


@pytest.mark.parametrize("formato", FORMATOS)
def test_modelo_traz_exatamente_as_colunas_canonicas(cliente_diretor, formato):
    resp = _baixar(cliente_diretor, formato)
    assert resp.status_code == 200 and "attachment" in resp["Content-Disposition"]
    linhas = ler_tabela(io.BytesIO(resp.content), f"modelo.{formato}", colunas=COLUNAS)
    assert set(linhas[0]) - {"_linha"} == set(COLUNAS)


@pytest.mark.parametrize("formato", FORMATOS)
def test_modelo_baixado_importa_sem_divergencia(cliente_diretor, diretor, formato):
    resp = _baixar(cliente_diretor, formato)
    linhas = ler_tabela(io.BytesIO(resp.content), f"modelo.{formato}", colunas=COLUNAS)
    kw = {"ano": 2026, "autor": diretor, "data_mudanca": __import__("datetime").date(2026, 3, 2)}
    r = importar_cadastro(linhas, gravar=True, **kw)
    assert r.criados == len(EXEMPLOS) and not r.inconsistentes and not r.divergencias
    assert all(a.pk.startswith("S") for a in Aluno.objects.all())
    r = importar_cadastro(linhas, gravar=True, **kw)
    assert r.sem_alteracao == len(EXEMPLOS) and not r.divergencias


@pytest.mark.parametrize("formato", FORMATOS)
def test_membro_recebe_403_e_anonimo_vai_para_login(client, membro, formato):
    url = reverse(f"web:cadastro_modelo_{formato}")
    resp = client.get(url)
    assert resp.status_code == 302 and reverse("web:login") in resp["Location"]
    client.force_login(membro)
    assert client.get(url).status_code == 403


def test_geradores_reutilizaveis_aceitam_colunas_quaisquer():
    cols, ex = ["a", "b"], [{"a": "1", "b": "2"}]
    assert gerar_modelo_csv(cols, ex).decode("utf-8-sig").splitlines()[0] == "a;b"
    assert ler_tabela(io.BytesIO(gerar_modelo_xlsx(cols, ex)), "m.xlsx")[0]["b"] == "2"


def test_pagina_de_importacao_tem_links_dos_modelos(cliente_diretor):
    html = cliente_diretor.get(reverse("web:cadastro_importar")).content.decode()
    assert "Baixar modelo (.xlsx)" in html and "Baixar modelo (.csv)" in html
