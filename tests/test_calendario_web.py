"""Telas do calendário letivo (RF007): leitura, importação e modelos."""

import io
from datetime import date

import pytest
from django.urls import reverse

from core.models import (
    CicloCalendario,
    DiaCalendario,
    PeriodoLetivo,
    RegistroAlteracao,
    RegistroImportacao,
    TemaRedacao,
)
from ingestao.calendario import TIPOS
from ingestao.leitura import ler_tabela
from tests.conftest import SENHA, importar_em_dois_passos

pytestmark = pytest.mark.django_db

ESCRITA = [
    ("web:calendario_importar", {}),
    ("web:calendario_item_novo", {"tipo": "dias"}),
    ("web:calendario_item_novo", {"tipo": "periodos"}),
    ("web:calendario_item_novo", {"tipo": "ciclos"}),
    ("web:calendario_item_novo", {"tipo": "temas"}),
    ("web:calendario_item", {"tipo": "dias", "pk": 1}),
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


def _importar(cliente, tipo, conteudo, ano=2026):
    return importar_em_dois_passos(
        cliente,
        reverse("web:calendario_importar"),
        lambda acao: {"tipo": tipo, "arquivo": _csv(conteudo), "ano": ano, "acao": acao},
    )


def test_importar_conferir_nao_grava(cliente_diretor):
    r = _enviar(cliente_diretor, "dias", _csv("data;dia_letivo\n16/02/2026;N\n"), "conferir")
    assert r.status_code == 200 and r.context["resumo"].criados == 1
    assert DiaCalendario.objects.count() == 0 and RegistroImportacao.objects.count() == 0


def test_importar_grava_e_registra_trilha(cliente_diretor, diretor):
    _importar(cliente_diretor, "dias", "data;dia_letivo\n16/02/2026;S\n")
    _importar(cliente_diretor, "dias", "data;dia_letivo\n16/02/2026;N\n")
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


def test_editar_registra_auditoria(cliente_diretor, diretor):
    dia = DiaCalendario.objects.create(data=date(2026, 2, 16), letivo=True)
    url = reverse("web:calendario_item", args=["dias", dia.pk])
    assert cliente_diretor.get(url).status_code == 200
    r = cliente_diretor.post(url, {"data": "2026-02-16", "descricao": "Carnaval"})
    assert r.status_code == 302
    dia.refresh_from_db()
    assert dia.letivo is False and dia.descricao == "Carnaval"
    campos = set(RegistroAlteracao.objects.filter(autor=diretor).values_list("campo", flat=True))
    assert campos == {"letivo", "descricao"}


def test_editar_tema_corrige_texto_e_data(cliente_diretor):
    tema = TemaRedacao.objects.create(data=date(2026, 2, 3), tema="Errado")
    url = reverse("web:calendario_item", args=["temas", tema.pk])
    cliente_diretor.post(url, {"data": "2026-02-10", "tema": "Certo"})
    tema.refresh_from_db()
    assert (tema.data, tema.tema) == (date(2026, 2, 10), "Certo")
    assert RegistroAlteracao.objects.filter(modelo="core.temaredacao").count() == 2


def test_tema_fora_da_terca_vira_erro_de_formulario(cliente_diretor):
    r = cliente_diretor.post(
        reverse("web:calendario_item_novo", args=["temas"]),
        {"data": "2026-02-02", "tema": "x"},
    )
    assert r.status_code == 200 and "terças-feiras" in r.content.decode()
    assert TemaRedacao.objects.count() == 0


def test_novo_dia_nao_audita(cliente_diretor):
    r = cliente_diretor.post(
        reverse("web:calendario_item_novo", args=["dias"]),
        {"data": "2026-02-16", "letivo": "on", "descricao": ""},
    )
    assert r.status_code == 302 and DiaCalendario.objects.count() == 1
    assert RegistroAlteracao.objects.count() == 0


def test_ciclo_sobreposto_vira_erro_de_formulario(cliente_diretor):
    CicloCalendario.objects.create(data_inicio=date(2026, 2, 2), data_fim=date(2026, 2, 15))
    r = cliente_diretor.post(
        reverse("web:calendario_item_novo", args=["ciclos"]),
        {"data_inicio": "2026-02-15", "data_fim": "2026-02-28"},
    )
    assert r.status_code == 200 and CicloCalendario.objects.count() == 1


def test_ciclo_simulado_fora_vira_erro_de_formulario(cliente_diretor):
    r = cliente_diretor.post(
        reverse("web:calendario_item_novo", args=["ciclos"]),
        {"data_inicio": "2026-02-02", "data_fim": "2026-02-15", "data_simulado": "2026-02-16"},
    )
    assert r.status_code == 200 and CicloCalendario.objects.count() == 0
    assert "A data do simulado deve estar dentro do ciclo." in r.content.decode()


def test_ciclo_fora_de_14_dias_salva_com_aviso(cliente_diretor):
    r = cliente_diretor.post(
        reverse("web:calendario_item_novo", args=["ciclos"]),
        {"data_inicio": "2026-02-02", "data_fim": "2026-02-10"},
        follow=True,
    )
    assert CicloCalendario.objects.count() == 1 and "9 dias" in r.content.decode()


def test_item_inexistente_ou_tipo_desconhecido_404(cliente_diretor):
    assert (
        cliente_diretor.get(reverse("web:calendario_item", args=["dias", 999])).status_code == 404
    )
    assert cliente_diretor.get(reverse("web:calendario_item_novo", args=["xx"])).status_code == 404


def test_nao_existe_rota_de_exclusao(cliente_diretor):
    dia = DiaCalendario.objects.create(data=date(2026, 2, 16), letivo=True)
    for sufixo in ("excluir/", "apagar/", "remover/"):
        url = reverse("web:calendario_item", args=["dias", dia.pk]) + sufixo
        assert cliente_diretor.post(url).status_code == 404
    r = cliente_diretor.post(
        reverse("web:calendario_item", args=["dias", dia.pk]), {"_delete": "1"}
    )
    assert DiaCalendario.objects.count() == 1 and r.status_code in (200, 302)


def test_tela_mostra_periodos_e_texto_da_regra(client, membro):
    PeriodoLetivo.objects.create(
        inicio=date(2026, 2, 2), fim=date(2026, 7, 3), descricao="Primeiro período"
    )
    client.force_login(membro)
    conteudo = client.get(reverse("web:calendario")).content.decode()
    assert "Primeiro período" in conteudo and "02/02/2026" in conteudo
    assert "segunda a sexta dentro dos períodos" in conteudo
    assert "Fins de semana sem registro" not in conteudo


def test_importar_periodos_e_trilha(cliente_diretor):
    r = _importar(
        cliente_diretor, "periodos", "inicio;fim;descricao\n02/02/2026;03/07/2026;Primeiro\n"
    )
    assert r.context["resumo"].criados == 1 and PeriodoLetivo.objects.count() == 1
    assert RegistroImportacao.objects.get().tipo == "PERIODOS"


def test_editar_periodo_audita_e_sobreposicao_vira_erro(cliente_diretor, diretor):
    a = PeriodoLetivo.objects.create(inicio=date(2026, 2, 2), fim=date(2026, 7, 3))
    PeriodoLetivo.objects.create(inicio=date(2026, 7, 20), fim=date(2026, 12, 11))
    url = reverse("web:calendario_item", args=["periodos", a.pk])
    assert cliente_diretor.get(url).status_code == 200
    r = cliente_diretor.post(url, {"inicio": "2026-02-02", "fim": "2026-07-25"})
    assert r.status_code == 200 and "sobrepõe" in r.content.decode()
    r = cliente_diretor.post(url, {"inicio": "2026-02-02", "fim": "2026-07-10"})
    assert r.status_code == 302
    campos = set(RegistroAlteracao.objects.filter(autor=diretor).values_list("campo", flat=True))
    assert campos == {"fim"}
