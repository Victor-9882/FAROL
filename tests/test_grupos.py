"""O curso em quatro grupos de presença × notas (RF010, RF011, RF012) (#92).

Base sintética (NF017). O Membro vê contagens e o plano sem nome nem matrícula (RN013).
"""

import re
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import Aluno, CicloCalendario, Turma
from inteligencia import ficha, grupos
from web import graficos
from web.templatetags.farol import indice, medidor, pontos

MATRICULA = re.compile(r"S26\d{4}")


@pytest.fixture
def base(diretor):
    from ingestao.demonstracao import carregar

    carregar(2026, autor=diretor)


def _ciclo(n):
    return CicloCalendario.objects.filter(data_inicio__year=2026).order_by("data_inicio")[n - 1]


# --- Regras (puras) ------------------------------------------------------------------


def test_indice_de_presenca_como_o_se_do_pei():
    assert grupos.indice_presenca(None) is None  # sem dia letivo no ciclo
    assert grupos.indice_presenca(Decimal(0)) == -1
    assert grupos.indice_presenca(Decimal("0.5")) == 0
    assert grupos.indice_presenca(Decimal("0.75")) == 0.5
    assert grupos.indice_presenca(Decimal(1)) == 1


def test_desvio_padrao_populacional():
    assert grupos.desvio_padrao([]) is None
    assert grupos.desvio_padrao([Decimal(5)]) is None
    assert grupos.desvio_padrao([3, 3, 3]) is None  # sem variação, sem escala
    assert grupos.desvio_padrao([Decimal(-10), Decimal(10)]) == 10


def test_indice_de_notas_como_o_sd_do_pei():
    assert grupos.indice_notas(Decimal(-10), 10) == -0.5  # meio desvio → z/2 = −0,5
    assert grupos.indice_notas(Decimal(20), 10) == 1  # dois desvios → +1
    assert grupos.indice_notas(Decimal(60), 10) == 1  # limitado
    assert grupos.indice_notas(Decimal(-60), 10) == -1
    assert grupos.indice_notas(None, 10) is None  # faltou ou primeiro simulado (RN009)
    assert grupos.indice_notas(Decimal(5), None) is None


def test_grupo_pelo_zero_de_cada_eixo():
    assert grupos.grupo(0, 0) == grupos.A  # o zero conta como "igual ou acima"
    assert grupos.grupo(0.3, -0.01) == grupos.B
    assert grupos.grupo(-0.01, 0) == grupos.C
    assert grupos.grupo(-0.5, -0.5) == grupos.D
    assert grupos.grupo(None, 0.5) is None and grupos.grupo(0.5, None) is None


def test_rotulos_so_descrevem_a_posicao():
    """RN012: nenhum rótulo sugere ação ("contato", "urgente") nem classifica o aluno."""
    for g in grupos.GRUPOS.values():
        texto = f"{g.nome} {g.presenca} {g.notas}".lower()
        assert not any(p in texto for p in ("contato", "urgente", "risco", "reforço"))


def test_contar():
    assert grupos.contar(["A", "A", None, "D"]) == {"A": 2, "B": 0, "C": 0, "D": 1, "fora": 1}


# --- Cálculo no banco ------------------------------------------------------------------


@pytest.mark.regras
@pytest.mark.django_db
def test_posicoes_seguem_rn008_e_rn009(base):
    oito = {p.aluno.pk: p for p in grupos.posicoes(2026, _ciclo(8))}
    queda = oito["S260006"]
    assert queda.delta == -60  # contra o último simulado do próprio aluno (RN008)
    assert queda.notas < 0 and queda.grupo in (grupos.B, grupos.D)
    sigma = grupos.desvio_padrao(p.delta for p in oito.values() if p.delta is not None)
    assert queda.notas == pytest.approx(max(-1, -60 / sigma / 2))
    assert queda.presenca == pytest.approx(float(2 * queda.frequencia.taxa - 1))
    seis = {p.aluno.pk: p for p in grupos.posicoes(2026, _ciclo(6))}
    assert seis["S260003"].delta is None and seis["S260003"].grupo is None  # faltou (RN009)
    assert all(p.grupo is None for p in grupos.posicoes(2026, _ciclo(1)))  # sem base


@pytest.mark.django_db
def test_distribuicao_por_ciclo_e_turma(base):
    serie = grupos.distribuicao(2026)
    assert [n for n, _, _ in serie] == list(range(1, 21))
    assert sum(serie[0][2][g] for g in grupos.GRUPOS) == 0  # primeiro simulado
    oito = serie[7][2]
    assert sum(oito[g] for g in grupos.GRUPOS) > 0
    turma = Turma.objects.get(ano=2026, nome="Turma A")
    so_a = grupos.distribuicao(2026, turma_id=turma.pk)[7][2]
    assert 0 < sum(so_a.values()) < sum(oito.values())


@pytest.mark.django_db
def test_ficha_traz_indices_e_grupo(base):
    dados = ficha.montar(Aluno.objects.get(pk="S260006"))
    oito = next(linha for linha in dados["linhas"] if linha.numero == 8)
    assert oito.indice_notas < 0 and oito.grupo in (grupos.B, grupos.D)
    posicao = next(p for p in grupos.posicoes(2026, _ciclo(8)) if p.aluno.pk == "S260006")
    assert oito.indice_notas == pytest.approx(posicao.notas)  # o mesmo índice do painel
    primeiro = dados["avaliadas"][0]
    assert primeiro.grupo is None  # sem simulado anterior
    assert dados["grupo_atual"] == dados["com_grupo"][-1]


# --- Telas -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_painel_mostra_os_quatro_grupos(cliente_diretor, base):
    html = cliente_diretor.get(reverse("web:inicio")).content.decode()
    assert "O curso em quatro grupos" in html and 'class="grafico plano"' in html
    for letra in grupos.GRUPOS:
        assert reverse("web:painel_grupo", args=[letra]) in html
    assert reverse("web:ficha", args=["S260006"]) in html  # o ponto abre a ficha
    turma = Turma.objects.get(ano=2026, nome="Turma A")
    url = reverse("web:inicio") + f"?ciclo={_ciclo(8).pk}&turma={turma.pk}"
    html = cliente_diretor.get(url).content.decode()
    assert "ciclo 8" in html and "Turma A ·" in html and "#c3cad5" in html  # outras turmas
    assert cliente_diretor.get(reverse("web:inicio") + "?turma=999999").status_code == 404
    html = cliente_diretor.get(reverse("web:inicio") + f"?ciclo={_ciclo(1).pk}").content.decode()
    assert "Ninguém entra nos grupos" in html


@pytest.mark.django_db
def test_lista_de_um_grupo(cliente_diretor, base):
    oito = _ciclo(8)
    posicoes = grupos.posicoes(2026, oito)
    alvo = next(p for p in posicoes if p.aluno.pk == "S260006")
    url = reverse("web:painel_grupo", args=[alvo.grupo]) + f"?ciclo={oito.pk}"
    resp = cliente_diretor.get(url)
    html = resp.content.decode()
    assert resp.status_code == 200 and alvo.aluno.nome in html and "indicativa" in html
    for p in posicoes:
        if p.grupo != alvo.grupo:
            assert p.aluno.matricula not in html
    assert cliente_diretor.get(reverse("web:painel_grupo", args=["E"])).status_code == 404
    assert cliente_diretor.get(reverse("web:painel_grupo", args=["a"])).status_code == 404
    sem_simulado = reverse("web:painel_grupo", args=["A"]) + "?ano=2030"
    assert cliente_diretor.get(sem_simulado).status_code == 404


@pytest.mark.django_db
def test_membro_ve_grupos_sem_nomes(client, membro, base):
    client.force_login(membro)
    html = client.get(reverse("web:inicio")).content.decode()
    assert "O curso em quatro grupos" in html and 'class="grafico plano"' in html
    assert not MATRICULA.search(html)
    assert not any(nome in html for nome in Aluno.objects.values_list("nome", flat=True))
    assert reverse("web:painel_grupo", args=["A"]) not in html and "/ficha/" not in html
    for letra in grupos.GRUPOS:
        assert client.get(reverse("web:painel_grupo", args=[letra])).status_code == 403


@pytest.mark.django_db
def test_ficha_mostra_a_trajetoria(cliente_diretor, base):
    html = cliente_diretor.get(reverse("web:ficha", args=["S260006"])).content.decode()
    assert "Trajetória nos quatro grupos" in html and "Índice de notas" in html
    assert 'class="grafico plano"' in html and "seta-trajetoria" in html


# --- Gráficos e filtros ----------------------------------------------------------------


def test_plano_escapa_e_so_liga_pontos_validos():
    ponto = {"presenca": 0.5, "notas": -0.2, "grupo": "B", "titulo": "<b>x</b>"}
    svg = graficos.plano([ponto | {"url": "/a?x=1&y=2"}], titulo="T&T")
    assert "<b>" not in svg and "&lt;b&gt;" in svg and "T&amp;T" in svg
    assert 'href="/a?x=1&amp;y=2"' in svg and "var(--grupo-b)" in svg
    sem = graficos.plano([ponto | {"notas": None}], titulo="T")
    assert "<circle" not in sem
    apagado = graficos.plano([ponto | {"url": "/a", "apagado": True}], titulo="T")
    assert "href" not in apagado and "#c3cad5" in apagado
    trajeto = graficos.plano(
        [ponto | {"rotulo": "7"}, ponto | {"presenca": 0.1, "rotulo": "8"}],
        titulo="T",
        trajetoria=True,
    )
    assert "<polyline" in trajeto and "marker-end" in trajeto and ">8</text>" in trajeto


def test_distribuicao_dos_grupos_em_barras():
    assert "sem dados" in graficos.distribuicao_grupos([], titulo="T")
    svg = graficos.distribuicao_grupos(
        [("C1", {"fora": 3}), ("C2", {"A": 1, "B": 3, "fora": 1})], titulo="T", destaque="C2"
    )
    assert svg.count("<rect") == 2 and "1 de 4 (25%)" in svg and "eixo destaque" in svg


def test_filtros_de_indice():
    assert indice(None) == "—" and indice(0.4249) == "+0,42" and indice(-1) == "−1,00"
    assert indice(0.001) == "0,00"
    assert pontos(None) == "—" and pontos(Decimal("-60.0")) == "−60" and pontos(12.5) == "+12,5"
    assert medidor(None) == ("50", "0")
    assert medidor(0.5) == ("50.0", "25.0") and medidor(-1) == ("0.0", "50.0")
