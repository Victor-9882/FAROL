"""Histórico de intervenções (RF020, NF007, RN013). Só dados sintéticos (NF017)."""

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import Aluno, Intervencao, Turma

pytestmark = pytest.mark.django_db

URL = "web:intervencoes"
Tipo = Intervencao.Tipo
Desfecho = Intervencao.Desfecho
BASE = date(2026, 5, 10)


@pytest.fixture
def aluno(turma_a):
    return Aluno.objects.create(
        matricula="S260001", nome="Ana Sintética", data_ingresso=date(2026, 2, 2), turma=turma_a
    )


@pytest.fixture
def outro(turma_a):
    return Aluno.objects.create(
        matricula="S260002", nome="Bruno Fictício", data_ingresso=date(2026, 2, 2), turma=turma_a
    )


def _crio(aluno, usuario, **kw):
    campos = {
        "responsavel": "Responsável Sintético",
        "tipo": Tipo.CONTATO,
        "data": BASE,
        "descricao": "Descrição sintética",
        "desfecho": "",
    }
    campos.update(kw)
    return Intervencao.objects.create(aluno=aluno, usuario=usuario, **campos)


def _get(cliente, **params):
    return cliente.get(reverse(URL), params)


def _ids(resp):
    return [i.pk for i in resp.context["pagina"]]


def test_membro_e_anonimo_nao_acessam(client, membro):
    assert client.get(reverse(URL)).status_code == 302
    client.force_login(membro)
    assert client.get(reverse(URL)).status_code == 403


def test_lista_tudo_sem_filtro_mais_recente_primeiro(cliente_diretor, aluno, outro, diretor):
    a = _crio(aluno, diretor, data=BASE)
    b = _crio(outro, diretor, data=BASE + timedelta(days=3))
    c = _crio(aluno, diretor, data=BASE)
    assert _ids(_get(cliente_diretor)) == [b.pk, c.pk, a.pk]


def test_filtra_por_matricula_exata(cliente_diretor, aluno, outro, diretor):
    a = _crio(aluno, diretor)
    _crio(outro, diretor)
    assert _ids(_get(cliente_diretor, aluno="S260001")) == [a.pk]
    assert _ids(_get(cliente_diretor, aluno="S2600")) == []


def test_filtra_por_parte_do_nome(cliente_diretor, aluno, outro, diretor):
    _crio(aluno, diretor)
    b = _crio(outro, diretor)
    assert _ids(_get(cliente_diretor, aluno="bruno")) == [b.pk]


@pytest.mark.parametrize("tipo", Tipo.values)
def test_filtra_por_tipo(cliente_diretor, aluno, diretor, tipo):
    alvo = _crio(aluno, diretor, tipo=tipo)
    for outro_tipo in set(Tipo.values) - {tipo}:
        _crio(aluno, diretor, tipo=outro_tipo)
    assert _ids(_get(cliente_diretor, tipo=tipo)) == [alvo.pk]


@pytest.mark.parametrize("desfecho", [*Desfecho.values, "PENDENTE"])
def test_filtra_por_desfecho(cliente_diretor, aluno, diretor, desfecho):
    valores = [*Desfecho.values, ""]
    por_valor = {v: _crio(aluno, diretor, desfecho=v) for v in valores}
    esperado = por_valor["" if desfecho == "PENDENTE" else desfecho]
    assert _ids(_get(cliente_diretor, desfecho=desfecho)) == [esperado.pk]


def test_periodo_inclui_as_duas_pontas(cliente_diretor, aluno, diretor):
    de, ate = date(2026, 5, 10), date(2026, 5, 20)
    _crio(aluno, diretor, data=de - timedelta(days=1))
    dentro_de = _crio(aluno, diretor, data=de)
    dentro_ate = _crio(aluno, diretor, data=ate)
    _crio(aluno, diretor, data=ate + timedelta(days=1))
    resp = _get(cliente_diretor, de=de.isoformat(), ate=ate.isoformat())
    assert sorted(_ids(resp)) == sorted([dentro_de.pk, dentro_ate.pk])


def test_periodo_invertido_mostra_erro(cliente_diretor, aluno, diretor):
    _crio(aluno, diretor)
    resp = _get(cliente_diretor, de="2026-06-01", ate="2026-05-01")
    assert resp.status_code == 200
    assert "ate" in resp.context["form"].errors
    assert _ids(resp) == []


def test_filtros_combinados(cliente_diretor, aluno, outro, diretor):
    alvo = _crio(aluno, diretor, tipo=Tipo.CONVERSA, desfecho=Desfecho.RESOLVIDO)
    _crio(outro, diretor, tipo=Tipo.CONVERSA, desfecho=Desfecho.RESOLVIDO)
    _crio(aluno, diretor, tipo=Tipo.CONTATO, desfecho=Desfecho.RESOLVIDO)
    _crio(aluno, diretor, tipo=Tipo.CONVERSA, desfecho=Desfecho.SEM_RETORNO)
    _crio(aluno, diretor, tipo=Tipo.CONVERSA, desfecho=Desfecho.RESOLVIDO, data=date(2025, 1, 1))
    resp = _get(
        cliente_diretor,
        aluno="S260001",
        tipo=Tipo.CONVERSA,
        desfecho=Desfecho.RESOLVIDO,
        de="2026-01-01",
    )
    assert _ids(resp) == [alvo.pk]


def test_historico_de_ano_anterior_aluno_nao_ativo_e_usuario_revogado_aparece(cliente_diretor):
    turma_antiga = Turma.objects.create(nome="Turma Antiga", ano=2024)
    antigo = Aluno.objects.create(
        matricula="S240001",
        nome="Carla Antiga",
        data_ingresso=date(2024, 2, 1),
        turma=turma_antiga,
        situacao=Aluno.Situacao.EVADIDO,
        data_saida=date(2024, 8, 1),
    )
    revogado = get_user_model().objects.create_user("exmembro", "ex@exemplo.org", "x-sintetica-1")
    revogado.is_active = False
    revogado.save()
    i = _crio(antigo, revogado, data=date(2024, 6, 1))
    resp = _get(cliente_diretor)
    assert _ids(resp) == [i.pk]
    assert "Carla Antiga" in resp.content.decode()


@pytest.mark.parametrize("metodo", ["post", "put", "delete"])
def test_so_aceita_get(cliente_diretor, metodo):
    assert getattr(cliente_diretor, metodo)(reverse(URL)).status_code == 405


def test_numero_de_consultas_nao_cresce_com_as_linhas(
    cliente_diretor, aluno, diretor, django_assert_max_num_queries
):
    for _ in range(3):
        _crio(aluno, diretor)
    with django_assert_max_num_queries(12):
        _get(cliente_diretor)
    for _ in range(20):
        _crio(aluno, diretor)
    with django_assert_max_num_queries(12):
        _get(cliente_diretor)


def test_paginacao_preserva_filtros(cliente_diretor, aluno, diretor):
    for _ in range(51):
        _crio(aluno, diretor, tipo=Tipo.CONVERSA)
    _crio(aluno, diretor, tipo=Tipo.OUTRO)
    resp = _get(cliente_diretor, tipo=Tipo.CONVERSA)
    assert len(resp.context["pagina"]) == 50
    assert "tipo=CONVERSA&amp;pagina=2" in resp.content.decode()
    resp2 = _get(cliente_diretor, tipo=Tipo.CONVERSA, pagina=2)
    assert len(resp2.context["pagina"]) == 1


def test_link_no_menu_so_para_diretor(client, diretor, membro):
    href = reverse(URL)
    client.force_login(membro)
    assert href not in client.get(reverse("web:turmas")).content.decode()
    client.force_login(diretor)
    assert href in client.get(reverse("web:turmas")).content.decode()


def test_ficha_tem_link_para_o_historico(cliente_diretor, aluno):
    resp = cliente_diretor.get(reverse("web:ficha", args=[aluno.matricula]))
    assert f"{reverse(URL)}?aluno=S260001" in resp.content.decode()
