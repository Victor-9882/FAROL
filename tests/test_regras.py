"""Parametrização dos limiares das regras de alerta (RF018, NF009, NF021) (#28).

Base sintética (NF017).
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import Alerta, RegistroAlteracao
from inteligencia import alertas, painel, regras
from inteligencia.models import RegraAlerta

pytestmark = pytest.mark.django_db

URL_FREQ = reverse("web:regra_editar", args=["FREQUENCIA"])
URL_DESEMP = reverse("web:regra_editar", args=["DESEMPENHO"])


@pytest.fixture
def base(diretor):
    from ingestao.demonstracao import carregar

    carregar(2026, autor=diretor)


def test_alterar_limiar_preserva_a_regra_antiga_e_audita(diretor):
    antiga = regras.vigente("FREQUENCIA")
    nova = regras.alterar_limiar("FREQUENCIA", Decimal(2), autor=diretor)
    antiga.refresh_from_db()
    assert not antiga.ativa and nova.ativa and nova.limiar == 2
    assert "pelo menos 2 faltas" in nova.descricao
    auditoria = RegistroAlteracao.objects.filter(modelo="inteligencia.regraalerta")
    assert set(auditoria.values_list("campo", "valor_anterior", "valor_novo")) == {
        ("ativa", "True", "False"),
        ("limiar", "3.00", "2.00"),
    }
    assert all(r.autor == diretor for r in auditoria)
    assert regras.alterar_limiar("FREQUENCIA", Decimal(2), autor=diretor) == nova  # sem mudança


def test_alterar_sem_regra_ativa_cria(diretor):
    RegraAlerta.objects.update(ativa=False)
    nova = regras.alterar_limiar("DESEMPENHO", Decimal(40), autor=diretor)
    assert nova.ativa and "40 pontos" in nova.descricao
    assert RegistroAlteracao.objects.get(campo="limiar").valor_anterior == ""


def test_descricao_sem_tipo_no_arquivo(tmp_path):
    arquivo = tmp_path / "r.yaml"
    arquivo.write_text("{}\n")
    assert regras.descricao_para("OUTRO", Decimal("2.50"), arquivo) == "Limiar: 2.5."


def test_simulacoes_nao_gravam(base):
    ref = painel.referencia()
    antes = Alerta.objects.count()
    um = alertas.simular_frequencia(ref.semanas_alerta, ref.ano, Decimal(1))
    tres = alertas.simular_frequencia(ref.semanas_alerta, ref.ano, Decimal(3))
    assert um >= tres >= 1
    queda_10 = alertas.simular_desempenho(ref.ciclo, Decimal(10))
    queda_30 = alertas.simular_desempenho(ref.ciclo, Decimal(30))
    assert queda_10 >= queda_30
    assert alertas.simular_frequencia(None, ref.ano, Decimal(1)) == 0
    assert alertas.simular_desempenho(None, Decimal(1)) == 0
    assert Alerta.objects.count() == antes


# --- Tela ------------------------------------------------------------------------------


def test_lista_de_regras_para_todos(client, membro, diretor):
    client.force_login(membro)
    html = client.get(reverse("web:regras")).content.decode()
    assert "Limiar: 3" in html and "Limiar: 30" in html and "Alterar o limiar" not in html
    assert client.get(URL_FREQ).status_code == 403
    assert (
        client.post(URL_FREQ, {"limiar": "2", "acao": "salvar", "previsto": "2.00"}).status_code
        == 403
    )
    assert regras.vigente("FREQUENCIA").limiar == 3


def test_previsualizar_e_salvar(cliente_diretor, base):
    previa = cliente_diretor.post(URL_FREQ, {"limiar": "2", "acao": "previsualizar"})
    html = previa.content.decode()
    assert "Salvar este limiar" in html and "aluno(s) seriam sinalizados" in html
    assert regras.vigente("FREQUENCIA").limiar == 3  # pré-visualizar não grava
    # salvar sem ter pré-visualizado o mesmo valor volta para a pré-visualização
    resp = cliente_diretor.post(URL_FREQ, {"limiar": "4", "acao": "salvar", "previsto": "2.00"})
    assert resp.status_code == 200 and regras.vigente("FREQUENCIA").limiar == 3
    antes = Alerta.objects.filter(tipo="FREQUENCIA", ativo=True).count()
    resp = cliente_diretor.post(
        URL_FREQ, {"limiar": "2", "acao": "salvar", "previsto": "2.00"}, follow=True
    )
    assert regras.vigente("FREQUENCIA").limiar == 2
    assert "alertas recalculados" in " ".join(str(m) for m in resp.context["messages"])
    assert Alerta.objects.filter(tipo="FREQUENCIA", ativo=True).count() >= antes
    html = cliente_diretor.get(reverse("web:regras")).content.decode()
    assert "Limiares anteriores" in html


@pytest.mark.parametrize(
    "url,valor,erro",
    [
        (URL_FREQ, "abc", "Informe um número"),
        (URL_FREQ, "0", "entre 1 e 7"),
        (URL_FREQ, "8", "entre 1 e 7"),
        (URL_FREQ, "2,5", "número inteiro de faltas"),
        (URL_DESEMP, "501", "entre 1 e 500"),
    ],
)
def test_valores_invalidos(cliente_diretor, url, valor, erro):
    resp = cliente_diretor.post(url, {"limiar": valor, "acao": "previsualizar"})
    assert erro in resp.content.decode()


def test_desempenho_aceita_decimal_e_tipo_invalido(cliente_diretor, base):
    html = cliente_diretor.post(
        URL_DESEMP, {"limiar": "25,5", "acao": "previsualizar"}
    ).content.decode()
    assert "25.5" in html or "25,5" in html
    cliente_diretor.post(URL_DESEMP, {"limiar": "25,5", "acao": "salvar", "previsto": "25.50"})
    assert regras.vigente("DESEMPENHO").limiar == Decimal("25.5")
    assert cliente_diretor.get(reverse("web:regra_editar", args=["EVOLUCAO"])).status_code == 404


def test_tela_sem_regra_ativa(cliente_diretor):
    RegraAlerta.objects.update(ativa=False)
    assert "Sem regra ativa" in cliente_diretor.get(reverse("web:regras")).content.decode()
    resp = cliente_diretor.get(URL_FREQ)
    assert resp.status_code == 200 and "Limiar atual" not in resp.content.decode()
