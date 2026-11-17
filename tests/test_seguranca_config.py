"""Sessão, cookies e HTTPS do deploy (RF001, NF013, NF014). Dados sintéticos."""

import secrets
from datetime import timedelta

import environ
import pytest
from django.contrib.sessions.models import Session
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from farol.seguranca import opcoes_de_seguranca
from tests.conftest import SENHA

VARIAVEIS = [
    "DJANGO_HTTPS",
    "DJANGO_SESSION_COOKIE_AGE",
    "DJANGO_SESSION_EXPIRE_AT_BROWSER_CLOSE",
    "DJANGO_SECURE_HSTS_SECONDS",
    "DJANGO_SECURE_PROXY_SSL_HEADER",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
]


@pytest.fixture
def ambiente(monkeypatch):
    """Ambiente limpo: o `.env` local já foi lido para `os.environ`."""
    for nome in VARIAVEIS:
        monkeypatch.delenv(nome, raising=False)
    return monkeypatch


def opcoes(debug):
    return opcoes_de_seguranca(environ.Env(), debug)


def test_padrao_de_producao_e_seguro(ambiente):
    o = opcoes(debug=False)
    assert o["SESSION_COOKIE_SECURE"] is True
    assert o["CSRF_COOKIE_SECURE"] is True
    assert o["SECURE_SSL_REDIRECT"] is True
    assert o["SECURE_HSTS_SECONDS"] == 2592000
    assert o["SESSION_COOKIE_AGE"] == 28800
    assert o["SESSION_EXPIRE_AT_BROWSER_CLOSE"] is True
    assert o["SECURE_PROXY_SSL_HEADER"] is None
    assert o["CSRF_TRUSTED_ORIGINS"] == []


def test_depuracao_desliga_https_por_padrao(ambiente):
    o = opcoes(debug=True)
    assert o["SESSION_COOKIE_SECURE"] is False
    assert o["CSRF_COOKIE_SECURE"] is False
    assert o["SECURE_SSL_REDIRECT"] is False
    assert o["SECURE_HSTS_SECONDS"] == 0
    assert o["SESSION_COOKIE_AGE"] == 28800
    assert o["SESSION_EXPIRE_AT_BROWSER_CLOSE"] is True


@pytest.mark.parametrize(("debug", "valor"), [(False, "False"), (True, "True")])
def test_django_https_explicito_vence_o_debug(ambiente, debug, valor):
    ambiente.setenv("DJANGO_HTTPS", valor)
    o = opcoes(debug=debug)
    esperado = valor == "True"
    assert o["SECURE_SSL_REDIRECT"] is esperado
    assert o["SESSION_COOKIE_SECURE"] is esperado
    assert (o["SECURE_HSTS_SECONDS"] > 0) is esperado


def test_proxy_so_e_confiado_quando_configurado(ambiente):
    assert opcoes(debug=False)["SECURE_PROXY_SSL_HEADER"] is None
    ambiente.setenv("DJANGO_SECURE_PROXY_SSL_HEADER", "True")
    assert opcoes(debug=False)["SECURE_PROXY_SSL_HEADER"] == ("HTTP_X_FORWARDED_PROTO", "https")


def test_origens_confiaveis_vem_do_ambiente(ambiente):
    ambiente.setenv("DJANGO_CSRF_TRUSTED_ORIGINS", "https://a.exemplo.org,https://b.exemplo.org")
    assert opcoes(debug=False)["CSRF_TRUSTED_ORIGINS"] == [
        "https://a.exemplo.org",
        "https://b.exemplo.org",
    ]


@pytest.mark.parametrize("idade", ["0", "-1"])
def test_idade_de_sessao_invalida_falha(ambiente, idade):
    ambiente.setenv("DJANGO_SESSION_COOKIE_AGE", idade)
    with pytest.raises(ImproperlyConfigured):
        opcoes(debug=False)


def test_idade_de_sessao_minima_e_aceita(ambiente):
    ambiente.setenv("DJANGO_SESSION_COOKIE_AGE", "1")
    assert opcoes(debug=False)["SESSION_COOKIE_AGE"] == 1


def test_check_deploy_sem_avisos_em_modo_producao(ambiente):
    producao = opcoes(debug=False)
    with override_settings(**producao, DEBUG=False, SECRET_KEY=secrets.token_urlsafe(64)):
        call_command("check", deploy=True, fail_level="WARNING")


def test_http_redireciona_para_https_exceto_saude(db, client, settings):
    settings.SECURE_SSL_REDIRECT = True
    resposta = client.get(reverse("web:login"))
    assert resposta.status_code == 301
    assert resposta["Location"].startswith("https://")
    assert client.get(reverse("web:saude")).status_code == 200


def test_resposta_https_traz_hsts(client, settings):
    settings.SECURE_HSTS_SECONDS = 2592000
    resposta = client.get(reverse("web:login"), secure=True)
    assert resposta["Strict-Transport-Security"] == "max-age=2592000"


def test_cookie_de_sessao_apos_login(client, diretor, settings):
    settings.SESSION_COOKIE_SECURE = True
    resposta = client.post(
        reverse("web:login"), {"username": diretor.username, "password": SENHA}, secure=True
    )
    assert resposta.status_code == 302
    cookie = resposta.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    assert cookie["max-age"] == ""
    assert cookie["secure"]
    assert client.session.get_expiry_age() == settings.SESSION_COOKIE_AGE


def test_sessao_vencida_no_servidor_volta_ao_login(cliente_diretor):
    Session.objects.update(expire_date=timezone.now() - timedelta(hours=1))
    resposta = cliente_diretor.get(reverse("web:inicio"))
    assert resposta.status_code == 302
    assert reverse("web:login") in resposta["Location"]
