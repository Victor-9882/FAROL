"""Fluxo de login do admin: uma única tela de entrada (RF001, NF013, NF014; issue #49)."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

SENHA = "senha-sintetica-123"  # nosec: dado de teste, sem relação com contas reais

pytestmark = pytest.mark.django_db


@pytest.fixture
def superusuario():
    return get_user_model().objects.create_superuser("root", "root@exemplo.org", SENHA)


@pytest.fixture
def staff():
    return get_user_model().objects.create_user(
        "equipe", "equipe@exemplo.org", SENHA, is_staff=True
    )


@pytest.mark.parametrize(
    "rota",
    ["/admin/", "/admin/core/usuario/", "/admin/password_change/", "/admin/jsi18n/"],
)
def test_admin_sem_login_termina_na_tela_de_entrada(client, rota):
    resposta = client.get(rota, follow=True)

    assert resposta.redirect_chain, "anônimo não pode receber 200 direto do admin"
    assert resposta.redirect_chain[-1][0] == f"/entrar/?next={rota}"
    assert resposta.status_code == 200
    assert resposta.request["PATH_INFO"] == "/entrar/"


def test_login_com_next_volta_ao_admin(client, superusuario):
    resposta = client.post("/entrar/?next=/admin/", {"username": "root", "password": SENHA})

    assert resposta.status_code == 302
    assert resposta["Location"] == "/admin/"
    assert client.get("/admin/").status_code == 200


def test_admin_login_nao_e_formulario(client):
    resposta = client.get("/admin/login/")

    assert resposta.status_code == 302
    assert resposta["Location"] == "/entrar/?next=/admin/"


def test_post_em_admin_login_nao_autentica(client, staff):
    resposta = client.post("/admin/login/", {"username": "equipe", "password": SENHA})

    assert resposta.status_code == 302
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("perfil", ["MEMBRO", "DIRETOR"])
def test_usuario_sem_is_staff_recebe_403_no_admin(client, perfil):
    usuario = get_user_model().objects.create_user(
        "comum", "comum@exemplo.org", SENHA, perfil=perfil
    )
    client.force_login(usuario)

    resposta = client.get("/admin/", follow=True)

    assert resposta.status_code == 403
    # Um único salto (admin -> /admin/login/) e nunca /entrar/, que formaria um laço.
    assert all(not url.startswith("/entrar/") for url, _ in resposta.redirect_chain)


def test_staff_autenticado_em_admin_login_vai_ao_indice(client, staff):
    client.force_login(staff)

    resposta = client.get("/admin/login/?next=/admin/core/usuario/")

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("admin:index")


def test_next_externo_e_descartado(client, superusuario):
    resposta = client.get("/admin/login/?next=https://externo.example/")
    assert resposta.status_code == 302

    resposta = client.post(resposta["Location"], {"username": "root", "password": SENHA})

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("web:inicio")


def test_staff_sem_superusuario_entra_no_admin_pelo_login_unico(client, staff):
    resposta = client.post("/entrar/?next=/admin/", {"username": "equipe", "password": SENHA})
    assert resposta["Location"] == "/admin/"

    assert client.get("/admin/").status_code == 200
