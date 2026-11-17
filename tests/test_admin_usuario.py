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


# --- Auditoria no admin (NF009, RF002) ---


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
    from core.models import RegistroAlteracao

    return RegistroAlteracao.objects.filter(modelo="core.usuario", objeto_id=str(usuario.pk))


def test_admin_alterar_perfil_gera_registro(client, superusuario, membro_staff):
    client.force_login(superusuario)
    client.post(_url_change(membro_staff), _dados_edicao(membro_staff, perfil="DIRETOR"))
    registro = _registros(membro_staff).get()
    assert registro.autor == superusuario
    assert (registro.campo, registro.valor_anterior, registro.valor_novo) == (
        "perfil",
        "MEMBRO",
        "DIRETOR",
    )


def test_admin_um_registro_por_campo_alterado(client, superusuario, membro_staff):
    client.force_login(superusuario)
    client.post(
        _url_change(membro_staff),
        _dados_edicao(
            membro_staff, perfil="DIRETOR", email="novo@exemplo.org", first_name="Fulano"
        ),
    )
    assert set(_registros(membro_staff).values_list("campo", flat=True)) == {
        "perfil",
        "email",
        "first_name",
    }


def test_admin_salvar_sem_mudanca_nao_gera_registro(client, superusuario, membro_staff):
    client.force_login(superusuario)
    resposta = client.post(_url_change(membro_staff), _dados_edicao(membro_staff))
    assert resposta.status_code == 302
    assert not _registros(membro_staff).exists()


@pytest.mark.parametrize("campo", ["is_staff", "is_superuser"])
def test_admin_promover_e_registrado(client, superusuario, campo):
    alvo = get_user_model().objects.create_user("alvo", "alvo@exemplo.org", SENHA, perfil="DIRETOR")
    client.force_login(superusuario)
    dados = _dados_edicao(alvo, is_staff=None)
    dados[campo] = "on"
    client.post(_url_change(alvo), dados)
    registro = _registros(alvo).get(campo=campo)
    assert (registro.valor_anterior, registro.valor_novo) == ("False", "True")
    assert registro.autor == superusuario


def test_admin_criar_usuario_registra_perfil(client, superusuario):
    client.force_login(superusuario)
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
    assert resposta.status_code == 302
    novo = get_user_model().objects.get(username="novo")
    registro = _registros(novo).get()
    assert (registro.campo, registro.valor_anterior, registro.valor_novo) == (
        "perfil",
        "",
        "DIRETOR",
    )


def test_admin_troca_de_senha_registra_sem_senha_nem_hash(client, superusuario, membro_staff):
    hash_antigo = membro_staff.password
    client.force_login(superusuario)
    url = reverse("admin:auth_user_password_change", args=[membro_staff.pk])
    resposta = client.post(url, {"password1": NOVA_SENHA, "password2": NOVA_SENHA})
    membro_staff.refresh_from_db()
    assert resposta.status_code == 302
    assert membro_staff.check_password(NOVA_SENHA)
    registro = _registros(membro_staff).get()
    assert registro.campo == "senha"
    assert registro.autor == superusuario
    for texto in (
        registro.campo,
        registro.valor_anterior,
        registro.valor_novo,
        registro.modelo,
        registro.objeto_id,
    ):
        assert NOVA_SENHA not in texto
        assert hash_antigo not in texto
        assert membro_staff.password not in texto


def test_admin_senha_invalida_nao_registra(client, superusuario, membro_staff):
    client.force_login(superusuario)
    url = reverse("admin:auth_user_password_change", args=[membro_staff.pk])
    client.post(url, {"password1": NOVA_SENHA, "password2": "diferente-789-abc"})
    membro_staff.refresh_from_db()
    assert membro_staff.check_password(SENHA)
    assert not _registros(membro_staff).exists()


def test_membro_staff_recusado_nao_gera_registro(client, membro_staff, diretor):
    from core.models import RegistroAlteracao

    client.force_login(membro_staff)
    client.post(_url_change(diretor), _dados_edicao(diretor, perfil="MEMBRO"))
    url = reverse("admin:auth_user_password_change", args=[diretor.pk])
    client.post(url, {"password1": NOVA_SENHA, "password2": NOVA_SENHA})
    assert not RegistroAlteracao.objects.exists()


def test_registro_do_admin_aparece_no_historico_da_tela(
    client, superusuario, membro_staff, diretor
):
    client.force_login(superusuario)
    client.post(_url_change(membro_staff), _dados_edicao(membro_staff, perfil="DIRETOR"))
    client.force_login(diretor)
    resposta = client.get(reverse("web:usuario_editar", args=[membro_staff.pk]))
    assert resposta.status_code == 200
    assert [r.campo for r in resposta.context["historico"]] == ["perfil"]


def test_constante_unica_de_campos_auditados():
    from core.auditoria import CAMPOS_AUDITADOS_USUARIO
    from web import forms

    assert forms.CAMPOS_AUDITADOS is CAMPOS_AUDITADOS_USUARIO
