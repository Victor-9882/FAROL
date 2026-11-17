"""Limite de tentativas de login com django-axes (RF001, NF013, NF014; issue #47)."""

import logging
from datetime import timedelta

import pytest
from axes.models import AccessAttempt
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

SENHA = "senha-sintetica-123"  # nosec: dado de teste, sem relação com contas reais
ERRADA = "senha-errada-sintetica"  # nosec: dado de teste
LIMITE = 3

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def limite_curto(settings):
    settings.AXES_FAILURE_LIMIT = LIMITE


def _entrar(client, usuario, senha=ERRADA, **extra):
    return client.post(reverse("web:login"), {"username": usuario, "password": senha}, **extra)


def _falhar(client, usuario, vezes, **extra):
    return [_entrar(client, usuario, **extra) for _ in range(vezes)]


def test_login_valido_antes_do_limite_funciona(client, diretor):
    _falhar(client, "diretor", LIMITE - 1)

    resposta = _entrar(client, "diretor", SENHA)

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("web:inicio")


def test_n_falhas_bloqueiam_e_a_senha_correta_e_recusada(client, diretor):
    ultima = _falhar(client, "diretor", LIMITE)[-1]

    assert ultima.status_code == 429
    assert "Muitas tentativas de entrada" in ultima.content.decode()

    certa = _entrar(client, "diretor", SENHA)
    assert certa.status_code == 429
    assert "_auth_user_id" not in client.session


def test_bloqueio_e_identico_para_usuario_inexistente(client, diretor):
    real = _falhar(client, "diretor", LIMITE)[-1]
    fantasma = _falhar(client, "fantasma", LIMITE)[-1]

    assert fantasma.status_code == real.status_code == 429
    assert fantasma.content == real.content


def test_mensagem_antes_do_bloqueio_e_a_generica(client, diretor):
    penultima = _falhar(client, "diretor", LIMITE - 1)[-1]

    assert penultima.status_code == 200
    corpo = penultima.content.decode()
    assert "Muitas tentativas" not in corpo
    assert "restantes" not in corpo
    assert penultima.context["form"].errors


def test_bloqueio_de_um_usuario_nao_afeta_outro(client, diretor, membro):
    _falhar(client, "diretor", LIMITE)

    resposta = _entrar(client, "membro", SENHA)

    assert resposta.status_code == 302


def test_bloqueio_vale_de_outro_ip(client, diretor):
    _falhar(client, "diretor", LIMITE)

    resposta = _entrar(client, "diretor", SENHA, REMOTE_ADDR="203.0.113.9")

    assert resposta.status_code == 429


def test_x_forwarded_for_nao_contorna_o_bloqueio(client, diretor):
    _falhar(client, "diretor", LIMITE)

    resposta = _entrar(client, "diretor", SENHA, HTTP_X_FORWARDED_FOR="198.51.100.7")

    assert resposta.status_code == 429


def test_bloqueio_expira_apos_o_resfriamento(client, diretor):
    _falhar(client, "diretor", LIMITE)
    assert _entrar(client, "diretor", SENHA).status_code == 429

    AccessAttempt.objects.update(attempt_time=timezone.now() - timedelta(minutes=16))

    assert _entrar(client, "diretor", SENHA).status_code == 302


def test_login_valido_zera_as_falhas(client, diretor):
    _falhar(client, "diretor", LIMITE - 1)
    assert _entrar(client, "diretor", SENHA).status_code == 302
    client.logout()

    # Se as falhas não tivessem sido zeradas, esta já bloquearia.
    _falhar(client, "diretor", LIMITE - 1)
    assert _entrar(client, "diretor", SENHA).status_code == 302


def test_tentativa_nao_guarda_senha_nem_token(client, diretor, caplog):
    caplog.set_level(logging.DEBUG)
    client.get(reverse("web:login"))
    token = client.cookies["csrftoken"].value
    _falhar(client, "diretor", LIMITE)

    tentativas = AccessAttempt.objects.all()
    assert tentativas.exists()
    guardado = " ".join(
        str(valor)
        for tentativa in tentativas
        for valor in (
            tentativa.username,
            tentativa.get_data,
            tentativa.post_data,
            tentativa.user_agent,
            tentativa.path_info,
        )
    )
    assert ERRADA not in guardado
    assert token not in guardado
    assert ERRADA not in caplog.text
    assert token not in caplog.text


def test_superusuario_desbloqueia_pelo_admin(client, diretor):
    root = get_user_model().objects.create_superuser("root", "root@exemplo.org", SENHA)
    _falhar(client, "diretor", LIMITE)
    assert _entrar(client, "diretor", SENHA).status_code == 429

    client.force_login(root)
    tentativa = AccessAttempt.objects.get(username="diretor")
    resposta = client.post(
        reverse("admin:axes_accessattempt_delete", args=[tentativa.pk]), {"post": "yes"}
    )
    assert resposta.status_code == 302
    client.logout()

    assert _entrar(client, "diretor", SENHA).status_code == 302


def test_staff_sem_permissao_nao_acessa_tentativas(client):
    staff = get_user_model().objects.create_user(
        "equipe", "equipe@exemplo.org", SENHA, is_staff=True
    )
    client.force_login(staff)

    resposta = client.get(reverse("admin:axes_accessattempt_changelist"))

    assert resposta.status_code == 403


def test_axes_reset_username_desbloqueia(client, diretor):
    _falhar(client, "diretor", LIMITE)
    assert _entrar(client, "diretor", SENHA).status_code == 429

    call_command("axes_reset_username", "diretor")

    assert _entrar(client, "diretor", SENHA).status_code == 302
