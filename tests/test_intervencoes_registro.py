"""Registro de intervenção e do desfecho (RF019, RN012, NF009). Só dados sintéticos (NF017)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from core.models import Alerta, Aluno, Intervencao, RegistroAlteracao, RegistroFrequencia

pytestmark = pytest.mark.django_db

Tipo = Intervencao.Tipo
Desfecho = Intervencao.Desfecho
SENHA = "senha-de-teste-123"


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


@pytest.fixture
def alerta(aluno):
    return Alerta.objects.create(
        aluno=aluno,
        tipo=Alerta.Tipo.FREQUENCIA,
        motivo="Motivo sintético",
        data_geracao=datetime(2026, 5, 11, 8, tzinfo=UTC),
        semana=date(2026, 5, 4),
    )


@pytest.fixture
def alerta_de_outro(outro):
    return Alerta.objects.create(
        aluno=outro,
        tipo=Alerta.Tipo.FREQUENCIA,
        motivo="Motivo sintético",
        data_geracao=datetime(2026, 5, 11, 8, tzinfo=UTC),
        semana=date(2026, 5, 4),
    )


def _url_nova(aluno):
    return reverse("web:intervencao_nova", args=[aluno.matricula])


def _url_desfecho(i):
    return reverse("web:intervencao_desfecho", args=[i.pk])


def _dados(**kw):
    dados = {
        "tipo": Tipo.CONVERSA,
        "data": timezone.localdate().isoformat(),
        "responsavel": "Responsável Sintético",
        "descricao": "Descrição sintética",
        "alerta": "",
        "desfecho": "",
    }
    dados.update(kw)
    return dados


def _crio(aluno, usuario, **kw):
    campos = {
        "responsavel": "Responsável Sintético",
        "tipo": Tipo.CONTATO,
        "data": date(2026, 5, 10),
        "descricao": "Descrição sintética",
        "desfecho": "",
    }
    campos.update(kw)
    return Intervencao.objects.create(aluno=aluno, usuario=usuario, **campos)


def test_membro_403_e_anonimo_302_nas_duas_rotas(client, membro, diretor, aluno):
    i = _crio(aluno, diretor)
    rotas = [_url_nova(aluno), _url_desfecho(i)]
    for url in rotas:
        assert client.get(url).status_code == 302
        assert client.post(url, _dados(desfecho=Desfecho.RESOLVIDO)).status_code == 302
    client.force_login(membro)
    for url in rotas:
        assert client.get(url).status_code == 403
        assert client.post(url, _dados(desfecho=Desfecho.RESOLVIDO)).status_code == 403
    assert Intervencao.objects.count() == 1
    i.refresh_from_db()
    assert i.desfecho == ""


def test_registra_com_tipo_data_responsavel_e_descricao(cliente_diretor, diretor, aluno):
    resp = cliente_diretor.post(_url_nova(aluno), _dados())
    assert resp.status_code == 302
    assert resp.url == reverse("web:ficha", args=[aluno.matricula])
    i = Intervencao.objects.get()
    assert i.aluno == aluno
    assert i.usuario == diretor
    assert i.tipo == Tipo.CONVERSA
    assert i.responsavel == "Responsável Sintético"
    assert i.desfecho == ""
    assert i.alerta is None


def test_registra_vinculada_ao_alerta_de_origem(cliente_diretor, aluno, alerta):
    resp = cliente_diretor.get(_url_nova(aluno), {"alerta": alerta.pk})
    assert resp.status_code == 200
    assert resp.context["form"].initial["alerta"] == alerta.pk
    cliente_diretor.post(_url_nova(aluno), _dados(alerta=alerta.pk))
    assert Intervencao.objects.get().alerta == alerta


def test_alerta_de_outro_aluno_e_recusado(cliente_diretor, aluno, alerta_de_outro):
    resp = cliente_diretor.post(_url_nova(aluno), _dados(alerta=alerta_de_outro.pk))
    assert resp.status_code == 200
    assert "alerta" in resp.context["form"].errors
    assert Intervencao.objects.count() == 0


@pytest.mark.parametrize("valor", ["abc", "999999", "OUTRO"])
def test_alerta_invalido_na_query_e_ignorado(cliente_diretor, aluno, alerta_de_outro, valor):
    if valor == "OUTRO":
        valor = alerta_de_outro.pk
    resp = cliente_diretor.get(_url_nova(aluno), {"alerta": valor})
    assert resp.status_code == 200
    assert not resp.context["form"].initial.get("alerta")


@pytest.mark.parametrize("campo", ["tipo", "data", "responsavel", "descricao"])
def test_campos_obrigatorios(cliente_diretor, aluno, campo):
    resp = cliente_diretor.post(_url_nova(aluno), _dados(**{campo: ""}))
    assert resp.status_code == 200
    assert campo in resp.context["form"].errors
    assert Intervencao.objects.count() == 0


def test_tipo_invalido_recusado(cliente_diretor, aluno):
    resp = cliente_diretor.post(_url_nova(aluno), _dados(tipo="PUNICAO"))
    assert resp.status_code == 200
    assert "tipo" in resp.context["form"].errors
    assert Intervencao.objects.count() == 0


def test_data_hoje_aceita_e_amanha_recusada(cliente_diretor, aluno):
    hoje = timezone.localdate()
    resp = cliente_diretor.post(
        _url_nova(aluno), _dados(data=(hoje + timedelta(days=1)).isoformat())
    )
    assert resp.status_code == 200
    assert "data" in resp.context["form"].errors
    assert Intervencao.objects.count() == 0
    resp = cliente_diretor.post(_url_nova(aluno), _dados(data=hoje.isoformat()))
    assert resp.status_code == 302
    assert Intervencao.objects.get().data == hoje


def test_desfecho_pode_vir_no_registro(cliente_diretor, aluno):
    cliente_diretor.post(_url_nova(aluno), _dados(desfecho=Desfecho.EM_ACOMPANHAMENTO))
    assert Intervencao.objects.get().desfecho == Desfecho.EM_ACOMPANHAMENTO


def test_desfecho_registrado_depois_e_auditado(cliente_diretor, diretor, aluno):
    i = _crio(aluno, diretor)
    resp = cliente_diretor.post(_url_desfecho(i), {"desfecho": Desfecho.RESOLVIDO})
    assert resp.status_code == 302
    assert resp.url == reverse("web:ficha", args=[aluno.matricula])
    i.refresh_from_db()
    assert i.desfecho == Desfecho.RESOLVIDO
    reg = RegistroAlteracao.objects.get()
    assert reg.modelo == "core.intervencao"
    assert reg.objeto_id == str(i.pk)
    assert reg.campo == "desfecho"
    assert reg.valor_anterior == ""
    assert reg.valor_novo == Desfecho.RESOLVIDO
    assert reg.autor == diretor


def test_desfecho_muda_de_em_acompanhamento_para_resolvido(cliente_diretor, diretor, aluno):
    i = _crio(aluno, diretor, desfecho=Desfecho.EM_ACOMPANHAMENTO)
    cliente_diretor.post(_url_desfecho(i), {"desfecho": Desfecho.RESOLVIDO})
    reg = RegistroAlteracao.objects.get()
    assert reg.valor_anterior == Desfecho.EM_ACOMPANHAMENTO
    assert reg.valor_novo == Desfecho.RESOLVIDO


def test_desfecho_nao_volta_a_pendente(cliente_diretor, diretor, aluno):
    i = _crio(aluno, diretor, desfecho=Desfecho.RESOLVIDO)
    resp = cliente_diretor.post(_url_desfecho(i), {"desfecho": ""})
    assert resp.status_code == 200
    assert "desfecho" in resp.context["form"].errors
    i.refresh_from_db()
    assert i.desfecho == Desfecho.RESOLVIDO
    assert RegistroAlteracao.objects.count() == 0


def test_desfecho_igual_nao_gera_auditoria(cliente_diretor, diretor, aluno):
    i = _crio(aluno, diretor, desfecho=Desfecho.RESOLVIDO)
    resp = cliente_diretor.post(_url_desfecho(i), {"desfecho": Desfecho.RESOLVIDO})
    assert resp.status_code == 302
    assert RegistroAlteracao.objects.count() == 0


def test_desfecho_so_altera_o_desfecho(cliente_diretor, diretor, aluno, outro):
    i = _crio(aluno, diretor)
    cliente_diretor.post(
        _url_desfecho(i),
        {
            "desfecho": Desfecho.SEM_RETORNO,
            "descricao": "Alterada",
            "tipo": Tipo.OUTRO,
            "aluno": outro.pk,
            "responsavel": "Outro",
        },
    )
    i.refresh_from_db()
    assert i.desfecho == Desfecho.SEM_RETORNO
    assert i.descricao == "Descrição sintética"
    assert i.tipo == Tipo.CONTATO
    assert i.aluno == aluno
    assert i.responsavel == "Responsável Sintético"
    assert list(RegistroAlteracao.objects.values_list("campo", flat=True)) == ["desfecho"]


def test_outro_diretor_registra_o_desfecho(client, diretor, aluno):
    outro_diretor = get_user_model().objects.create_user(
        "diretor2", "diretor2@exemplo.org", SENHA, perfil="DIRETOR"
    )
    i = _crio(aluno, diretor)
    client.force_login(outro_diretor)
    client.post(_url_desfecho(i), {"desfecho": Desfecho.RESOLVIDO})
    assert RegistroAlteracao.objects.get().autor == outro_diretor
    i.refresh_from_db()
    assert i.usuario == diretor


def test_aluno_invalido_ou_inexistente_da_404(cliente_diretor, aluno):
    aluno.situacao = Aluno.Situacao.INVALIDO
    aluno.save()
    assert cliente_diretor.get(_url_nova(aluno)).status_code == 404
    assert cliente_diretor.post(_url_nova(aluno), _dados()).status_code == 404
    assert cliente_diretor.get(reverse("web:intervencao_nova", args=["S269999"])).status_code == 404
    assert (
        cliente_diretor.get(reverse("web:intervencao_desfecho", args=[999999])).status_code == 404
    )
    assert Intervencao.objects.count() == 0


def test_aluno_desligado_pode_receber_intervencao(cliente_diretor, aluno):
    aluno.situacao = Aluno.Situacao.DESLIGADO
    aluno.data_saida = date(2026, 4, 1)
    aluno.save()
    assert cliente_diretor.post(_url_nova(aluno), _dados()).status_code == 302
    assert Intervencao.objects.count() == 1


def test_rn012_registrar_nao_altera_aluno_nem_alerta(cliente_diretor, aluno, alerta):
    antes = (aluno.situacao, aluno.data_saida, alerta.ativo)
    resp = cliente_diretor.get(_url_nova(aluno))
    assert "RN012" in resp.content.decode()
    cliente_diretor.post(_url_nova(aluno), _dados(alerta=alerta.pk))
    aluno.refresh_from_db()
    alerta.refresh_from_db()
    assert (aluno.situacao, aluno.data_saida, alerta.ativo) == antes


def test_ficha_painel_e_historico_tem_os_links(cliente_diretor, diretor, aluno, alerta):
    i = _crio(aluno, diretor)
    RegistroFrequencia.objects.create(aluno=aluno, data=date(2026, 5, 8), presente=False)
    ficha = cliente_diretor.get(reverse("web:ficha", args=[aluno.matricula])).content.decode()
    assert f"{_url_nova(aluno)}?alerta={alerta.pk}" in ficha
    assert _url_nova(aluno) in ficha
    assert _url_desfecho(i) in ficha
    painel = cliente_diretor.get(reverse("web:painel_lista", args=["FREQUENCIA"])).content.decode()
    assert f"{_url_nova(aluno)}?alerta={alerta.pk}" in painel
    historico = cliente_diretor.get(reverse("web:intervencoes")).content.decode()
    assert _url_desfecho(i) in historico


def test_mensagem_de_sucesso_sem_nome_nem_matricula(cliente_diretor, aluno):
    resp = cliente_diretor.post(_url_nova(aluno), _dados(), follow=True)
    textos = [str(m) for m in resp.context["messages"]]
    assert textos == ["Intervenção registrada."]
    assert aluno.nome not in textos[0] and aluno.matricula not in textos[0]
    i = Intervencao.objects.get()
    resp = cliente_diretor.post(_url_desfecho(i), {"desfecho": Desfecho.RESOLVIDO}, follow=True)
    assert [str(m) for m in resp.context["messages"]] == ["Desfecho registrado."]
