"""E-mail de fechamento do ciclo (RF017, #32). Base sintética (NF017); sem dado nominal (RN013)."""

import json
import os
import urllib.request
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import override_settings

from core.historico import ExclusaoProibidaError
from core.models import Aluno, CicloCalendario
from inteligencia import painel
from relatorios.models import NotificacaoCiclo
from relatorios.notificacoes import (
    ciclo_a_notificar,
    destinatarios,
    notificar_fechamento,
    resumo_do_ciclo,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def base(diretor, membro):
    from ingestao.demonstracao import carregar

    carregar(2026, autor=diretor)


@pytest.fixture
def ciclo(base):
    """O ciclo mais recente com resultados de simulado."""
    return painel.referencia().ciclo


@pytest.fixture
def dia_seguinte(ciclo):
    return ciclo.data_fim + timedelta(days=1)


def test_ciclo_que_termina_hoje_ainda_nao_fechou(ciclo):
    assert ciclo_a_notificar(ciclo.data_fim).data_fim < ciclo.data_fim  # só um ciclo anterior
    notificar_fechamento(ciclo.data_fim)
    assert not NotificacaoCiclo.objects.filter(ciclo=ciclo).exists()


def test_dia_seguinte_ao_fim_envia(ciclo, dia_seguinte):
    assert ciclo_a_notificar(dia_seguinte) == ciclo
    r = notificar_fechamento(dia_seguinte)
    assert r["status"] == "enviado" and r["ciclo"] == ciclo
    assert len(mail.outbox) == r["destinatarios"] == 2


def test_ciclo_sem_resultados_aguarda(db, diretor):
    c = CicloCalendario.objects.create(
        data_inicio=date(2026, 3, 2), data_fim=date(2026, 3, 13), data_simulado=date(2026, 3, 13)
    )
    assert ciclo_a_notificar(c.data_fim + timedelta(days=1)) is None
    assert notificar_fechamento(c.data_fim + timedelta(days=1))["status"] == "sem_ciclo"
    assert mail.outbox == []


def test_email_nao_tem_nome_nem_matricula(base, dia_seguinte):
    notificar_fechamento(dia_seguinte)
    assert mail.outbox
    for m in mail.outbox:
        texto = m.subject + "\n" + m.body
        for nome, matricula in Aluno.objects.values_list("nome", "matricula"):
            assert nome not in texto and matricula not in texto


def test_email_traz_contagens_por_turma_e_total(ciclo, dia_seguinte):
    resumo = resumo_do_ciclo(ciclo)
    turmas, total = painel.situacao(
        painel.Referencia(ano=2026, ciclo=ciclo, numero_ciclo=resumo.numero)
    )
    assert resumo.total.alunos == total.total_alunos
    assert resumo.total.queda == total.contagem("queda")
    assert [t.turma for t in resumo.turmas] == [t.turma for t in turmas]
    notificar_fechamento(dia_seguinte)
    corpo = mail.outbox[0].body
    assert f"TOTAL ({total.total_alunos} alunos)" in corpo
    assert f"- Queda de desempenho: {total.contagem('queda')}" in corpo
    for t in turmas:
        assert f"{t.turma} ({t.total_alunos} alunos)" in corpo
    assert mail.outbox[0].subject.startswith(f"FAROL: fechamento do ciclo {resumo.numero} (")
    assert "indicativos" in corpo


def test_destinatarios_so_ativos_com_email_sem_superusuario(base):
    modelo = get_user_model()
    modelo.objects.create_user("inativo", "inativo@exemplo.org", "x", is_active=False)
    modelo.objects.create_superuser("admin", "admin@exemplo.org", "x")
    modelo.objects.create_user("semmail", "", "x")
    assert destinatarios() == ["diretor@exemplo.org", "membro@exemplo.org"]


def test_uma_mensagem_por_destinatario(base, dia_seguinte):
    notificar_fechamento(dia_seguinte)
    assert {m.to[0] for m in mail.outbox} == {"diretor@exemplo.org", "membro@exemplo.org"}
    assert all(len(m.to) == 1 and not m.cc and not m.bcc for m in mail.outbox)


def test_segunda_execucao_nao_reenvia(ciclo, dia_seguinte):
    notificar_fechamento(dia_seguinte)
    enviados = len(mail.outbox)
    assert notificar_fechamento(dia_seguinte)["status"] == "sem_ciclo"
    assert len(mail.outbox) == enviados
    assert NotificacaoCiclo.objects.filter(ciclo=ciclo).count() == 1


def test_reenviar_forca(base, ciclo, dia_seguinte, diretor):
    notificar_fechamento(dia_seguinte)
    get_user_model().objects.create_user("novo", "novo@exemplo.org", "x")
    mail.outbox.clear()
    r = notificar_fechamento(dia_seguinte, reenviar=True)
    assert r["status"] == "enviado" and r["ciclo"] == ciclo and len(mail.outbox) == 3
    assert NotificacaoCiclo.objects.get(ciclo=ciclo).destinatarios == 3


def test_so_o_ciclo_mais_recente_e_notificado(ciclo, dia_seguinte):
    anteriores = CicloCalendario.objects.filter(
        data_inicio__lt=ciclo.data_inicio, simulados__isnull=False
    ).distinct()
    assert anteriores.exists()
    notificar_fechamento(dia_seguinte + timedelta(days=60))
    assert list(NotificacaoCiclo.objects.values_list("ciclo", flat=True)) == [ciclo.pk]
    assert not NotificacaoCiclo.objects.filter(ciclo__in=anteriores).exists()


def test_falha_de_smtp_nao_registra(ciclo, dia_seguinte, monkeypatch):
    def falha(self, mensagens):
        raise OSError("smtp indisponível")

    monkeypatch.setattr("django.core.mail.backends.locmem.EmailBackend.send_messages", falha)
    with pytest.raises(OSError):
        notificar_fechamento(dia_seguinte)
    assert not NotificacaoCiclo.objects.exists()


def test_sem_destinatarios_nao_registra(base, dia_seguinte):
    get_user_model().objects.update(is_active=False)
    assert notificar_fechamento(dia_seguinte)["status"] == "sem_destinatarios"
    assert not NotificacaoCiclo.objects.exists() and mail.outbox == []


def test_link_so_com_site_url(base, dia_seguinte):
    notificar_fechamento(dia_seguinte)
    assert "Painel:" not in mail.outbox[0].body
    mail.outbox.clear()
    with override_settings(SITE_URL="https://farol.exemplo.org/"):
        notificar_fechamento(dia_seguinte, reenviar=True)
    assert "Painel: https://farol.exemplo.org/\n" in mail.outbox[0].body


def test_comando_notificar_ciclo(base, dia_seguinte, capsys):
    call_command("notificar_ciclo", data=dia_seguinte.isoformat())
    saida = capsys.readouterr().out
    assert "2 destinatário(s)" in saida and "@" not in saida
    call_command("notificar_ciclo", data=(dia_seguinte).isoformat(), reenviar=True)
    assert "2 destinatário(s)" in capsys.readouterr().out
    call_command("notificar_ciclo", data="2020-01-01")
    assert "Nada enviado" in capsys.readouterr().out


def test_comando_data_invalida(base):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("notificar_ciclo", data="ontem")


def test_comando_sem_destinatarios(base, dia_seguinte, capsys):
    get_user_model().objects.update(is_active=False)
    call_command("notificar_ciclo", data=dia_seguinte.isoformat())
    assert "Nenhum destinatário" in capsys.readouterr().out


def test_registro_nao_guarda_enderecos_e_nao_se_exclui(ciclo, dia_seguinte):
    notificar_fechamento(dia_seguinte)
    campos = {f.name for f in NotificacaoCiclo._meta.get_fields()}
    assert campos == {"id", "criado_em", "ciclo", "destinatarios"}
    with pytest.raises(ExclusaoProibidaError):
        NotificacaoCiclo.objects.get().delete()


@pytest.mark.skipif(not os.environ.get("MAILPIT_URL"), reason="sem MAILPIT_URL")
def test_entrega_no_mailpit(ciclo, dia_seguinte):
    base_url = os.environ["MAILPIT_URL"].rstrip("/")
    antes = json.load(urllib.request.urlopen(f"{base_url}/api/v1/messages"))["total"]
    with override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"):
        notificar_fechamento(dia_seguinte)
    depois = json.load(urllib.request.urlopen(f"{base_url}/api/v1/messages"))["total"]
    assert depois > antes
