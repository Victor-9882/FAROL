"""Painel (RF010), indicadores agregados (RF012) e ficha do aluno (RF011, RF013) (#20 a #23).

Base sintética (NF017). O Membro nunca vê nome nem matrícula (RN013, NF013).
"""

import re
import time
from datetime import date, timedelta

import pytest
from django.urls import reverse

from core.models import Aluno, CicloCalendario, RegistroImportacao, Turma
from inteligencia import ficha, painel
from web import graficos
from web.templatetags.farol import dictkey

pytestmark = pytest.mark.django_db

MATRICULA = re.compile(r"S26\d{4}")


@pytest.fixture
def base(diretor):
    from ingestao.demonstracao import carregar

    carregar(2026, autor=diretor)


def _ciclo(n):
    return CicloCalendario.objects.filter(data_inicio__year=2026).order_by("data_inicio")[n - 1]


def _nomes():
    return list(Aluno.objects.values_list("nome", flat=True))


# --- Cálculos --------------------------------------------------------------------------


def test_referencia_e_situacao_dos_perfis(base):
    ref = painel.referencia()
    assert ref.ano == 2026 and ref.ciclo is not None and ref.semana.weekday() == 0
    ciclo8 = painel.Referencia(ano=2026, semana=None, ciclo=_ciclo(8), numero_ciclo=8)
    turmas, total = painel.situacao(ciclo8)
    assert sum(t.total_alunos for t in turmas) == total.total_alunos
    assert "S260006" in {a.pk for a in total.alunos["queda"]}  # queda de 60 (RN008)
    ciclo6 = painel.Referencia(ano=2026, ciclo=_ciclo(6), numero_ciclo=6)
    _, total6 = painel.situacao(ciclo6)
    assert "S260003" in {a.pk for a in total6.alunos["sem_avaliacao"]}  # faltou (RN009)
    primeiro = painel.Referencia(ano=2026, ciclo=_ciclo(1), numero_ciclo=1)
    _, total1 = painel.situacao(primeiro)
    assert total1.contagem("sem_avaliacao") == total1.total_alunos  # sem base de comparação


def test_sem_dados(db):
    ref = painel.referencia(2030)
    assert ref.semana is None and ref.ciclo is None
    assert painel.situacao(ref) == ([], painel.Situacao(turma="Total"))
    assert painel.alertas_ativos(ref) == {"FREQUENCIA": [], "DESEMPENHO": []}


def test_sem_regra_nao_classifica(base):
    from inteligencia.models import RegraAlerta

    RegraAlerta.objects.update(ativa=False)
    ref = painel.Referencia(ano=2026, ciclo=_ciclo(8), numero_ciclo=8)
    _, total = painel.situacao(ref)
    assert total.contagem("queda") == 0 and total.contagem("sem_avaliacao") == total.total_alunos


def test_evolucao_por_turma_e_area(base):
    ciclos, series = painel.evolucao(2026)
    assert len(ciclos) == 20 and list(series)[-1] == "Total"
    assert all(len(pontos) == 20 for pontos in series.values())
    assert series["Total"][7].queda >= 1 and series["Total"][0].queda == 0
    turma = Turma.objects.get(ano=2026, nome="Turma A")
    _, so_a = painel.evolucao(2026, turma_id=turma.pk, area="MATEMATICA")
    assert "Turma A" in so_a and so_a["Total"][0].nota is not None


def test_ficha_do_aluno(base):
    dados = ficha.montar(Aluno.objects.get(pk="S260006"))
    oito = next(linha for linha in dados["linhas"] if linha.numero == 8)
    assert oito.classificacao == "QUEDA" and oito.delta_total.valor == -60
    assert oito.media_turma is not None  # referência da turma (RF013)
    ausente = ficha.montar(Aluno.objects.get(pk="S260003"))
    seis = next(linha for linha in ausente["linhas"] if linha.numero == 6)
    assert seis.avaliado and seis.total is None and seis.delta_total is None  # RN009
    chamada = ficha.montar(Aluno.objects.get(pk="S260005"))  # segunda chamada
    assert min(linha.ciclo.data_fim for linha in chamada["linhas"]) >= date(2026, 3, 9)


# --- Telas: Diretor ----------------------------------------------------------------------


def test_painel_do_diretor(cliente_diretor, base):
    inicio = time.perf_counter()
    html = cliente_diretor.get(reverse("web:inicio")).content.decode()
    assert time.perf_counter() - inicio < 5  # NF010
    assert "Alertas ativos" in html and "indicativos" in html and "dados nominais" in html
    assert reverse("web:painel_lista", args=["FREQUENCIA"]) in html
    assert "Situação das turmas no ciclo 20" in html


def test_listas_do_diretor(cliente_diretor, base):
    ref = painel.referencia()
    resp = cliente_diretor.get(reverse("web:painel_lista", args=["FREQUENCIA"]))
    assert resp.status_code == 200
    for alerta in painel.alertas_ativos(ref)["FREQUENCIA"]:
        assert alerta.motivo in resp.content.decode()  # NF004
    resp = cliente_diretor.get(
        reverse("web:painel_lista", args=["sem_avaliacao"]) + "?turma=Turma A"
    )
    assert resp.status_code == 200 and "Turma A" in resp.content.decode()
    assert cliente_diretor.get(reverse("web:painel_lista", args=["xyz"])).status_code == 404
    url = reverse("web:painel_lista", args=["queda"]) + "?turma=Inexistente"
    assert cliente_diretor.get(url).status_code == 404


def test_ficha_na_tela(cliente_diretor, base):
    resp = cliente_diretor.get(reverse("web:ficha", args=["S260006"]))
    html = resp.content.decode()
    assert resp.status_code == 200 and "<svg" in html and "Média da turma (referência)" in html
    assert Aluno.objects.get(pk="S260006").nome in html and "Queda" in html
    assert cliente_diretor.get(reverse("web:ficha", args=["S269999"])).status_code == 404


def test_ficha_sem_dados(cliente_diretor, turma_a):
    Aluno.objects.create(
        matricula="S260001", nome="Sem Dados", data_ingresso=date(2026, 2, 2), turma=turma_a
    )
    html = cliente_diretor.get(reverse("web:ficha", args=["S260001"])).content.decode()
    assert "Nenhum resultado de simulado" in html and "sem dados" in html


def test_painel_sem_dados_mostra_ultima_importacao(cliente_diretor, diretor):
    html = cliente_diretor.get(reverse("web:inicio") + "?ano=2030").content.decode()
    assert "Sem dados no período" in html and "Nenhuma importação registrada" in html
    RegistroImportacao.objects.create(
        autor=diretor, tipo="FREQUENCIA", nome_arquivo="g.xlsx", tamanho_bytes=1, ano=2030
    )
    html = cliente_diretor.get(reverse("web:inicio") + "?ano=2030").content.decode()
    assert "Frequência (catraca): " in html


def test_indicadores_com_filtros(cliente_diretor, base):
    turma = Turma.objects.get(ano=2026, nome="Turma B")
    url = reverse("web:indicadores")
    html = cliente_diretor.get(url).content.decode()
    assert "<svg" in html and "Evolução no tempo" in html
    html = cliente_diretor.get(
        f"{url}?turma={turma.pk}&area=NATUREZA&ciclo={_ciclo(8).pk}"
    ).content.decode()
    assert "Ciclo 8:" in html and "Ciências da Natureza" in html
    assert cliente_diretor.get(f"{url}?turma=999999").status_code == 404
    assert cliente_diretor.get(f"{url}?area=FISICA").status_code == 404
    assert "Ainda não há resultados" in cliente_diretor.get(f"{url}?ano=2030").content.decode()


# --- RN013: o Membro só vê agregados (#29) ----------------------------------------------


def test_membro_ve_so_agregados(client, membro, base):
    client.force_login(membro)
    for url in (
        reverse("web:inicio"),
        reverse("web:indicadores"),
        reverse("web:indicadores") + f"?ciclo={_ciclo(8).pk}",
    ):
        resp = client.get(url)
        html = resp.content.decode()
        assert resp.status_code == 200
        assert not MATRICULA.search(html), url
        assert not any(nome in html for nome in _nomes()), url
        assert reverse("web:painel_lista", args=["FREQUENCIA"]) not in html
    for url in (
        reverse("web:painel_lista", args=["FREQUENCIA"]),
        reverse("web:painel_lista", args=["queda"]),
        reverse("web:ficha", args=["S260006"]),
    ):
        assert client.get(url).status_code == 403


def test_sem_login_nada_responde(client, base):
    for url in (
        reverse("web:inicio"),
        reverse("web:indicadores"),
        reverse("web:ficha", args=["S260006"]),
    ):
        resp = client.get(url)
        assert resp.status_code == 302 and "/entrar/" in resp["Location"]


# --- Gráfico e filtro ------------------------------------------------------------------


def test_grafico_escapa_e_trata_vazio():
    assert "sem dados" in graficos.linhas([], {}, titulo="T")
    assert "sem dados" in graficos.linhas(["C1"], {"a": [None]}, titulo="T")
    svg = graficos.linhas(
        ["C1", "C2", "C3"], {"<b>x</b>": [1, None, 3], "y": [2, 2, 2]}, titulo="T&T"
    )
    assert "<b>" not in svg and "&lt;b&gt;" in svg and svg.count("<polyline") == 3
    assert "T&amp;T" in svg


def test_filtro_dictkey():
    assert dictkey({"a": [1]}, "a") == [1] and dictkey({}, "a") == [] and dictkey(None, "a") == []


def test_alertas_de_frequencia_das_semanas_do_ciclo(base):
    ref = painel.referencia()
    inicio, fim = ref.semanas_alerta
    assert inicio.weekday() == 0 and inicio <= ref.ciclo.data_inicio and fim == ref.semana
    alertas = painel.alertas_ativos(ref)["FREQUENCIA"]
    assert alertas and all(inicio <= a.semana <= fim for a in alertas)
    sem_ciclo = painel.Referencia(ano=2026, semana=ref.semana)
    assert sem_ciclo.semanas_alerta[0] == ref.semana - timedelta(days=7)
    assert painel.Referencia(ano=2026).semanas_alerta is None
