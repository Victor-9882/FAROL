"""Justificativa de falta (#17; RF008, RN002, RN004, RN005, NF005, NF007, NF009). Só dados
sintéticos (NF017)."""

from datetime import date, timedelta

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from core.models import (
    Alerta,
    Aluno,
    DiaCalendario,
    PeriodoLetivo,
    RegistroAlteracao,
    RegistroFrequencia,
    Turma,
)
from ingestao import justificativas
from ingestao.justificativas import JustificativaRecusada
from inteligencia import alertas, consultas

pytestmark = pytest.mark.django_db

SEG = date(2026, 3, 2)
DOMINGO = SEG + timedelta(days=6)


@pytest.fixture
def aluno(db):
    PeriodoLetivo.objects.create(inicio=date(2026, 2, 2), fim=date(2026, 11, 27))
    turma = Turma.objects.create(nome="Turma 1", ano=2026)
    return Aluno.objects.create(
        matricula="S260001", nome="Aluno Sintético Um", data_ingresso=date(2026, 2, 2), turma=turma
    )


def _semana(aluno, codigos, segunda=SEG):
    for n, c in enumerate(codigos):
        RegistroFrequencia.objects.update_or_create(
            aluno=aluno,
            data=segunda + timedelta(days=n),
            defaults={"presente": c == "P", "justificada": c == "J"},
        )


def _registro(aluno, dia):
    return RegistroFrequencia.objects.get(aluno=aluno, data=dia)


def _url(aluno):
    return reverse("web:faltas", args=[aluno.matricula])


def _post(cliente, aluno, registro, acao="justificar"):
    return cliente.post(_url(aluno), {"registro": registro.pk, "acao": acao})


def _frequencia(aluno):
    return consultas.frequencias([aluno], SEG, DOMINGO)[aluno.pk]


# --- RN002: os dois ramos -------------------------------------------------------------


@pytest.mark.regras
def test_rn002_falta_justificada_conta_como_presenca_e_a_sem_justificativa_nao(
    cliente_diretor, aluno
):
    _semana(aluno, "PFFPP")
    antes = _frequencia(aluno)
    assert (antes.percentual, antes.faltas, antes.justificadas) == (60.0, 2, 0)
    _post(cliente_diretor, aluno, _registro(aluno, SEG + timedelta(days=1)))
    depois = _frequencia(aluno)
    assert (depois.percentual, depois.faltas, depois.justificadas) == (80.0, 1, 1)


@pytest.mark.regras
def test_rn002_justificar_no_limiar_desativa_o_alerta_e_retirar_reativa(cliente_diretor, aluno):
    _semana(aluno, "PFFFP")
    alertas.gerar_frequencia(SEG, 2026)
    alerta = Alerta.objects.get()
    assert alerta.ativo
    registro = _registro(aluno, SEG + timedelta(days=1))
    _post(cliente_diretor, aluno, registro)
    alerta.refresh_from_db()
    assert alerta.ativo is False  # sem exclusão (NF007)
    _post(cliente_diretor, aluno, registro, "retirar")
    alerta.refresh_from_db()
    assert alerta.ativo is True
    assert Alerta.objects.count() == 1  # NF005


@pytest.mark.regras
def test_rn002_acima_do_limiar_o_alerta_continua(cliente_diretor, aluno):
    _semana(aluno, "FFFFP")
    alertas.gerar_frequencia(SEG, 2026)
    _post(cliente_diretor, aluno, _registro(aluno, SEG))
    alerta = Alerta.objects.get()
    assert alerta.ativo and "3 falta(s)" in alerta.motivo


@pytest.mark.regras
def test_rn005_falta_em_dia_nao_letivo_nao_aparece_nem_e_justificada(cliente_diretor, aluno):
    _semana(aluno, "PFPPP")
    terca = SEG + timedelta(days=1)
    registro = _registro(aluno, terca)
    DiaCalendario.objects.create(data=terca, letivo=False, descricao="Emenda")
    assert registro not in justificativas.faltas_do_aluno(aluno)
    resposta = _post(cliente_diretor, aluno, registro)
    assert resposta.status_code == 302
    registro.refresh_from_db()
    assert registro.justificada is False
    assert not RegistroAlteracao.objects.exists()
    with pytest.raises(JustificativaRecusada):
        justificativas.justificar(registro, autor=None)


def test_rn004_falta_fora_da_janela_do_aluno_nao_aparece(aluno):
    aluno.data_ingresso = SEG + timedelta(days=1)
    aluno.data_saida = SEG + timedelta(days=3)
    aluno.situacao = Aluno.Situacao.DESLIGADO
    aluno.save()
    _semana(aluno, "FFFFF")
    datas = [r.data for r in justificativas.faltas_do_aluno(aluno)]
    assert datas == [SEG + timedelta(days=3), SEG + timedelta(days=2), SEG + timedelta(days=1)]
    with pytest.raises(JustificativaRecusada):
        justificativas.justificar(_registro(aluno, SEG), autor=None)
    with pytest.raises(JustificativaRecusada):
        justificativas.justificar(_registro(aluno, SEG + timedelta(days=4)), autor=None)


def test_lista_do_mais_recente_ao_mais_antigo_e_so_faltas(aluno):
    _semana(aluno, "FPJFP")
    datas = [r.data for r in justificativas.faltas_do_aluno(aluno)]
    assert datas == [SEG + timedelta(days=3), SEG + timedelta(days=2), SEG]


# --- NF009 ----------------------------------------------------------------------------


def test_nf009_justificar_grava_autor_data_e_valor_anterior(cliente_diretor, diretor, aluno):
    _semana(aluno, "PFPPP")
    registro = _registro(aluno, SEG + timedelta(days=1))
    _post(cliente_diretor, aluno, registro)
    auditoria = RegistroAlteracao.objects.get()
    assert auditoria.modelo == "core.registrofrequencia"
    assert auditoria.objeto_id == str(registro.pk) and auditoria.campo == "justificada"
    assert (auditoria.valor_anterior, auditoria.valor_novo) == ("False", "True")
    assert auditoria.autor == diretor and auditoria.criado_em is not None


def test_nf009_retirar_grava_o_inverso(cliente_diretor, aluno):
    _semana(aluno, "PJPPP")
    registro = _registro(aluno, SEG + timedelta(days=1))
    _post(cliente_diretor, aluno, registro, "retirar")
    auditoria = RegistroAlteracao.objects.get()
    assert (auditoria.valor_anterior, auditoria.valor_novo) == ("True", "False")
    registro.refresh_from_db()
    assert registro.justificada is False and registro.presente is False


def test_repetir_a_acao_nao_gera_auditoria(cliente_diretor, aluno):
    _semana(aluno, "PFPPP")
    registro = _registro(aluno, SEG + timedelta(days=1))
    _post(cliente_diretor, aluno, registro)
    resposta = _post(cliente_diretor, aluno, registro)
    assert RegistroAlteracao.objects.count() == 1
    mensagens = [str(m) for m in get_messages(resposta.wsgi_request)]
    assert "Nada a alterar." in mensagens


# --- Recusas --------------------------------------------------------------------------


def test_presenca_nao_pode_ser_justificada(cliente_diretor, aluno):
    _semana(aluno, "PPPPP")
    registro = _registro(aluno, SEG)
    _post(cliente_diretor, aluno, registro)
    registro.refresh_from_db()
    assert registro.justificada is False
    assert not RegistroAlteracao.objects.exists()
    with pytest.raises(JustificativaRecusada):
        justificativas.justificar(registro, autor=None)


def test_registro_de_outro_aluno_da_404(cliente_diretor, aluno):
    outro = Aluno.objects.create(
        matricula="S260002", nome="Aluno Dois", data_ingresso=date(2026, 2, 2), turma=aluno.turma
    )
    _semana(outro, "FPPPP")
    registro = _registro(outro, SEG)
    assert _post(cliente_diretor, aluno, registro).status_code == 404
    registro.refresh_from_db()
    assert registro.justificada is False


def test_acao_desconhecida_da_400(cliente_diretor, aluno):
    _semana(aluno, "FPPPP")
    assert _post(cliente_diretor, aluno, _registro(aluno, SEG), "apagar").status_code == 400
    assert not RegistroAlteracao.objects.exists()


def test_aluno_inexistente_da_404(cliente_diretor):
    assert cliente_diretor.get(reverse("web:faltas", args=["S269999"])).status_code == 404


# --- Acesso (RN013) e conteúdo --------------------------------------------------------


def test_membro_403_e_anonimo_302_em_get_e_post(client, membro, aluno):
    _semana(aluno, "FPPPP")
    registro = _registro(aluno, SEG)
    dados = {"registro": registro.pk, "acao": "justificar"}
    assert client.get(_url(aluno)).status_code == 302
    assert client.post(_url(aluno), dados).status_code == 302
    client.force_login(membro)
    assert client.get(_url(aluno)).status_code == 403
    assert client.post(_url(aluno), dados).status_code == 403
    registro.refresh_from_db()
    assert registro.justificada is False and not RegistroAlteracao.objects.exists()


def test_metodo_nao_permitido(cliente_diretor, aluno):
    assert cliente_diretor.delete(_url(aluno)).status_code == 405


def test_tela_lista_as_faltas_e_explica_a_regra(cliente_diretor, aluno):
    _semana(aluno, "FJPPP")
    html = cliente_diretor.get(_url(aluno)).content.decode()
    assert "Falta" in html and "Justificada" in html
    assert "A justificativa aprovada conta como presença (RN002)." in html
    assert reverse("web:ficha", args=[aluno.matricula]) in html


def test_mensagem_sem_nome_nem_matricula(cliente_diretor, aluno):
    _semana(aluno, "FPPPP")
    resposta = _post(cliente_diretor, aluno, _registro(aluno, SEG))
    texto = " ".join(str(m) for m in get_messages(resposta.wsgi_request))
    assert "Falta justificada." in texto
    assert aluno.nome not in texto and aluno.matricula not in texto


def test_ficha_tem_link_para_as_faltas(cliente_diretor, aluno):
    html = cliente_diretor.get(reverse("web:ficha", args=[aluno.matricula])).content.decode()
    assert _url(aluno) in html and "Faltas e justificativas" in html
