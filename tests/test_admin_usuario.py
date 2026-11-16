"""Admin de Usuario: só superusuário gerencia contas e perfil (RF001, RN013, NF013)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

SENHA = "senha-sintetica-123"  # nosec: dado de teste, sem relação com contas reais
NOVA_SENHA = "outra-senha-sintetica-456"  # nosec: dado de teste

pytestmark = pytest.mark.django_db


@pytest.fixture
def membro_staff():
    usuario = get_user_model().objects.create_user(
        "membro", "membro@exemplo.org", SENHA, is_staff=True
    )
    usuario.user_permissions.set(
        Permission.objects.filter(content_type__app_label="core", content_type__model="usuario")
    )
    return usuario


@pytest.fixture
def diretor():
    return get_user_model().objects.create_user(
        "diretor", "diretor@exemplo.org", SENHA, perfil="DIRETOR"
    )


@pytest.fixture
def superusuario():
    return get_user_model().objects.create_superuser("root", "root@exemplo.org", SENHA)


def _url_change(usuario):
    return reverse("admin:core_usuario_change", args=[usuario.pk])


def test_membro_staff_ve_o_proprio_usuario_somente_leitura(client, membro_staff):
    client.force_login(membro_staff)
    resposta = client.get(_url_change(membro_staff))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert 'name="perfil"' not in html
    assert 'name="is_superuser"' not in html


@pytest.mark.parametrize(
    "dados",
    [{"perfil": "DIRETOR"}, {"is_superuser": "on"}, {"user_permissions": [1]}],
)
def test_membro_staff_nao_se_promove_por_post(client, membro_staff, dados):
    client.force_login(membro_staff)
    resposta = client.post(_url_change(membro_staff), dados)
    membro_staff.refresh_from_db()
    assert resposta.status_code == 403
    assert membro_staff.perfil == "MEMBRO"
    assert membro_staff.is_diretor is False
    assert membro_staff.is_superuser is False


def test_membro_staff_nao_troca_senha_do_diretor(client, membro_staff, diretor):
    client.force_login(membro_staff)
    url = reverse("admin:auth_user_password_change", args=[diretor.pk])
    resposta = client.post(url, {"password1": NOVA_SENHA, "password2": NOVA_SENHA})
    diretor.refresh_from_db()
    assert resposta.status_code == 403
    assert diretor.check_password(SENHA)


def test_membro_staff_nao_cria_usuario_diretor(client, membro_staff):
    client.force_login(membro_staff)
    antes = get_user_model().objects.count()
    resposta = client.post(
        reverse("admin:core_usuario_add"),
        {
            "username": "novo",
            "password1": NOVA_SENHA,
            "password2": NOVA_SENHA,
            "email": "novo@exemplo.org",
            "perfil": "DIRETOR",
        },
    )
    assert resposta.status_code == 403
    assert get_user_model().objects.count() == antes


def test_membro_staff_nao_exclui_usuario(client, membro_staff, diretor):
    client.force_login(membro_staff)
    url = reverse("admin:core_usuario_delete", args=[diretor.pk])
    resposta = client.post(url, {"post": "yes"})
    assert resposta.status_code == 403
    assert get_user_model().objects.filter(pk=diretor.pk).exists()


def test_superusuario_ve_perfil_editavel(client, superusuario, membro_staff):
    client.force_login(superusuario)
    resposta = client.get(_url_change(membro_staff))
    assert resposta.status_code == 200
    assert 'name="perfil"' in resposta.content.decode()


def test_superusuario_altera_o_perfil(client, superusuario, membro_staff):
    client.force_login(superusuario)
    resposta = client.post(
        _url_change(membro_staff),
        {
            "username": membro_staff.username,
            "email": membro_staff.email,
            "perfil": "DIRETOR",
            "is_active": "on",
            "is_staff": "on",
            "date_joined_0": "2026-01-01",
            "date_joined_1": "00:00:00",
            "_save": "Salvar",
        },
    )
    membro_staff.refresh_from_db()
    assert resposta.status_code == 302
    assert membro_staff.perfil == "DIRETOR"
