"""Testes da estrutura inicial do projeto (#4)."""

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

CAMADAS = ["core", "ingestao", "inteligencia", "relatorios", "web"]


def test_check_do_django_sem_erros():
    call_command("check", fail_level="WARNING")


@pytest.mark.parametrize("app", CAMADAS)
def test_app_de_cada_camada_instalado(app):
    assert apps.is_installed(app)


@pytest.mark.django_db
def test_rota_de_saude_responde_ok(client):
    resposta = client.get(reverse("web:saude"))
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_modelo_de_usuario_e_o_do_farol():
    assert get_user_model()._meta.label == "core.Usuario"


@pytest.mark.django_db
def test_usuario_novo_tem_o_perfil_mais_restrito():
    """Sem perfil explícito, o usuário não vê dados nominais (RN013)."""
    usuario = get_user_model().objects.create_user("membro", "membro@exemplo.org", "x")
    assert usuario.perfil == "MEMBRO"
    assert not usuario.is_diretor


@pytest.mark.django_db
def test_diretor_e_reconhecido():
    usuario = get_user_model().objects.create_user(
        "diretor", "diretor@exemplo.org", "x", perfil="DIRETOR"
    )
    assert usuario.is_diretor
