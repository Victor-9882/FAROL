"""Autenticação e perfis Diretor/Membro (RF001, RN013, NF013, NF014)."""

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse

SENHA = "senha-sintetica-123"  # nosec: dado de teste, sem relação com contas reais
ROTAS_PUBLICAS = {"web:saude", "web:login"}


@pytest.fixture
def diretor(db):
    return get_user_model().objects.create_user(
        "diretor", "diretor@exemplo.org", SENHA, perfil="DIRETOR"
    )


@pytest.fixture
def membro(db):
    return get_user_model().objects.create_user("membro", "membro@exemplo.org", SENHA)


def _rotas_sem_parametros(resolver=None, prefixo="", namespace=""):
    """Percorre o URLconf e devolve (nome, caminho) das rotas do app `web`."""
    resolver = resolver or get_resolver()
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            ns = f"{namespace}{p.namespace}:" if p.namespace else namespace
            yield from _rotas_sem_parametros(p, prefixo + str(p.pattern), ns)
        elif isinstance(p, URLPattern) and p.name and "<" not in str(p.pattern):
            yield f"{namespace}{p.name}", "/" + prefixo + str(p.pattern)


# --- NF014: nada responde sem autenticação -------------------------------------------


@pytest.mark.django_db
def test_toda_rota_do_web_exige_login_exceto_as_publicas(client):
    rotas = [(n, c) for n, c in _rotas_sem_parametros() if n.startswith("web:")]
    assert rotas, "nenhuma rota encontrada"
    for nome, caminho in rotas:
        resposta = client.get(caminho)
        if nome in ROTAS_PUBLICAS:
            assert resposta.status_code == 200, nome
        else:
            assert resposta.status_code == 302, nome
            assert resposta["Location"].startswith(reverse("web:login")), nome


@pytest.mark.django_db
def test_pagina_inicial_sem_login_redireciona_para_o_login(client):
    resposta = client.get(reverse("web:inicio"))
    assert resposta.status_code == 302
    assert resposta["Location"] == f"{reverse('web:login')}?next={reverse('web:inicio')}"


@pytest.mark.django_db
def test_admin_tambem_exige_login(client):
    resposta = client.get("/admin/")
    assert resposta.status_code == 302


# --- Login e logout ------------------------------------------------------------------


def test_tela_de_login_abre_sem_autenticacao(client):
    resposta = client.get(reverse("web:login"))
    assert resposta.status_code == 200
    assert "Entrar" in resposta.content.decode()


@pytest.mark.parametrize("perfil_fixture", ["diretor", "membro"])
def test_login_valido_leva_a_pagina_inicial(client, request, perfil_fixture):
    usuario = request.getfixturevalue(perfil_fixture)
    resposta = client.post(reverse("web:login"), {"username": usuario.username, "password": SENHA})
    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("web:inicio")
    assert client.get(reverse("web:inicio")).status_code == 200


def test_login_com_senha_errada_nao_autentica(client, diretor):
    resposta = client.post(reverse("web:login"), {"username": "diretor", "password": "errada"})
    assert resposta.status_code == 200
    assert "_auth_user_id" not in client.session
    assert client.get(reverse("web:inicio")).status_code == 302


def test_login_nao_redireciona_para_site_externo(client, diretor):
    resposta = client.post(
        reverse("web:login") + "?next=https://externo.example/",
        {"username": "diretor", "password": SENHA},
    )
    assert resposta["Location"] == reverse("web:inicio")


def test_logout_encerra_a_sessao(client, diretor):
    client.force_login(diretor)
    resposta = client.post(reverse("web:logout"))
    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("web:login")
    assert client.get(reverse("web:inicio")).status_code == 302


def test_logout_por_get_nao_encerra_a_sessao(client, diretor):
    client.force_login(diretor)
    assert client.get(reverse("web:logout")).status_code == 405
    assert client.get(reverse("web:inicio")).status_code == 200


def test_usuario_inativo_nao_entra(client, diretor):
    diretor.is_active = False
    diretor.save()
    client.post(reverse("web:login"), {"username": "diretor", "password": SENHA})
    assert "_auth_user_id" not in client.session


# --- RN013 / NF013: dados nominais só para o Diretor ---------------------------------


@override_settings(ROOT_URLCONF="tests.urls_acesso")
def test_rota_nominal_sem_login_redireciona(client):
    resposta = client.get("/nominal/ficha/")
    assert resposta.status_code == 302
    assert resposta["Location"].startswith(reverse("web:login"))


@override_settings(ROOT_URLCONF="tests.urls_acesso")
def test_membro_nunca_recebe_nome_ou_matricula_por_url_direta(client, membro):
    client.force_login(membro)
    resposta = client.get("/nominal/ficha/")
    assert resposta.status_code == 403
    corpo = resposta.content.decode()
    assert "Aluno Sintético" not in corpo
    assert "S0001" not in corpo


@override_settings(ROOT_URLCONF="tests.urls_acesso")
def test_diretor_acessa_rota_nominal(client, diretor):
    client.force_login(diretor)
    resposta = client.get("/nominal/ficha/")
    assert resposta.status_code == 200
    assert resposta.json()["matricula"] == "S0001"


@override_settings(ROOT_URLCONF="tests.urls_acesso")
def test_perfil_alterado_para_membro_perde_acesso_na_hora(client, diretor):
    client.force_login(diretor)
    assert client.get("/nominal/ficha/").status_code == 200
    diretor.perfil = "MEMBRO"
    diretor.save()
    assert client.get("/nominal/ficha/").status_code == 403


def test_pagina_inicial_mostra_o_perfil_do_usuario(client, membro, diretor):
    client.force_login(membro)
    assert "Membro de diretoria" in client.get(reverse("web:inicio")).content.decode()
    client.force_login(diretor)
    assert "Diretor" in client.get(reverse("web:inicio")).content.decode()
