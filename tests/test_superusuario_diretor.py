"""Superusuário exige perfil Diretor, garantido no banco (RF001, RN013, NF013)."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse

from core.models import RegistroAlteracao

SENHA = "senha-sintetica-123"  # nosec: dado de teste, sem relação com contas reais
MENSAGEM = "Superusuário precisa ter o perfil Diretor."

pytestmark = pytest.mark.django_db


def _modelo():
    return get_user_model()


@pytest.fixture
def superusuario():
    return _modelo().objects.create_superuser("root", "root@exemplo.org", SENHA)


def _url_change(usuario):
    return reverse("admin:core_usuario_change", args=[usuario.pk])


def _dados_edicao(usuario, **extra):
    dados = {
        "username": usuario.username,
        "email": usuario.email,
        "perfil": usuario.perfil,
        "is_active": "on",
        "is_staff": "on",
        "date_joined_0": "2026-01-01",
        "date_joined_1": "00:00:00",
        "_save": "Salvar",
    }
    dados.update(extra)
    return {k: v for k, v in dados.items() if v is not None}


def _registros(usuario):
    return RegistroAlteracao.objects.filter(modelo="core.usuario", objeto_id=str(usuario.pk))


def test_create_superuser_cria_diretor():
    usuario = _modelo().objects.create_superuser("root", "root@exemplo.org", SENHA)
    assert usuario.perfil == "DIRETOR"
    assert usuario.is_superuser is True


def test_create_superuser_recusa_perfil_membro():
    with pytest.raises(ValueError, match="perfil Diretor"):
        _modelo().objects.create_superuser("root", "root@exemplo.org", SENHA, perfil="MEMBRO")
    assert not _modelo().objects.exists()


def test_comando_createsuperuser_cria_diretor():
    call_command(
        "createsuperuser", interactive=False, username="cli", email="cli@exemplo.org", verbosity=0
    )
    assert _modelo().objects.get(username="cli").perfil == "DIRETOR"


@pytest.mark.parametrize(
    ("perfil", "superusuario", "valida"),
    [
        ("MEMBRO", False, True),
        ("DIRETOR", False, True),
        ("DIRETOR", True, True),
        ("MEMBRO", True, False),
    ],
)
def test_as_quatro_combinacoes_de_superusuario_e_perfil(perfil, superusuario, valida):
    usuario = _modelo()(
        username="alvo", email="alvo@exemplo.org", perfil=perfil, is_superuser=superusuario
    )
    usuario.set_password(SENHA)
    if valida:
        usuario.full_clean()
        usuario.save()
        assert _modelo().objects.filter(username="alvo").exists()
    else:
        with pytest.raises(ValidationError, match=MENSAGEM):
            usuario.full_clean()


def test_banco_recusa_rebaixar_superusuario(superusuario):
    with pytest.raises(IntegrityError), transaction.atomic():
        _modelo().objects.filter(pk=superusuario.pk).update(perfil="MEMBRO")


def test_banco_recusa_promover_membro_a_superusuario():
    membro = _modelo().objects.create_user("membro", "membro@exemplo.org", SENHA)
    with pytest.raises(IntegrityError), transaction.atomic():
        _modelo().objects.filter(pk=membro.pk).update(is_superuser=True)


def test_admin_recusa_promover_membro_a_superusuario(client, superusuario):
    alvo = _modelo().objects.create_user("alvo", "alvo@exemplo.org", SENHA)
    client.force_login(superusuario)
    resposta = client.post(_url_change(alvo), _dados_edicao(alvo, is_superuser="on"))
    alvo.refresh_from_db()
    assert resposta.status_code == 200
    assert MENSAGEM in resposta.content.decode()
    assert alvo.is_superuser is False
    assert not _registros(alvo).exists()


def test_admin_recusa_rebaixar_superusuario_mantendo_o_flag(client, superusuario):
    client.force_login(superusuario)
    resposta = client.post(
        _url_change(superusuario),
        _dados_edicao(superusuario, perfil="MEMBRO", is_superuser="on"),
    )
    superusuario.refresh_from_db()
    assert resposta.status_code == 200
    assert (superusuario.perfil, superusuario.is_superuser) == ("DIRETOR", True)
    assert not _registros(superusuario).exists()


def test_admin_promove_diretor_a_superusuario(client, superusuario):
    alvo = _modelo().objects.create_user("alvo", "alvo@exemplo.org", SENHA, perfil="DIRETOR")
    client.force_login(superusuario)
    resposta = client.post(_url_change(alvo), _dados_edicao(alvo, is_superuser="on"))
    alvo.refresh_from_db()
    assert resposta.status_code == 302
    assert alvo.is_superuser is True
    registro = _registros(alvo).get(campo="is_superuser")
    assert (registro.valor_anterior, registro.valor_novo) == ("False", "True")


def test_admin_rebaixa_e_tira_superusuario_no_mesmo_post(client, superusuario):
    alvo = _modelo().objects.create_superuser("alvo", "alvo@exemplo.org", SENHA)
    client.force_login(superusuario)
    resposta = client.post(_url_change(alvo), _dados_edicao(alvo, perfil="MEMBRO"))
    alvo.refresh_from_db()
    assert resposta.status_code == 302
    assert (alvo.perfil, alvo.is_superuser) == ("MEMBRO", False)
    assert set(_registros(alvo).values_list("campo", flat=True)) == {"perfil", "is_superuser"}


def test_superusuario_acessa_rota_nominal_por_ser_diretor(client, superusuario):
    client.force_login(superusuario)
    assert superusuario.is_diretor is True
    assert client.get(reverse("web:intervencoes")).status_code == 200
