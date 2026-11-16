"""Autenticação e perfis Diretor/Membro (RF001, RN013, NF013, NF014)."""

from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.urls.converters import get_converters
from django.utils.html import escape

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


_ARGUMENTO_FICTICIO = {
    "int": 1,
    "str": "x",
    "slug": "x",
    "uuid": UUID("00000000-0000-4000-8000-000000000001"),
    "path": "x",
}


def _argumentos_ficticios(padrao):
    """Argumentos fictícios por conversor (int->1, str/slug/path->"x", uuid fixo)."""
    kwargs = {}
    for nome, conversor in padrao.converters.items():
        chave = next(k for k, v in get_converters().items() if v.__class__ is conversor.__class__)
        kwargs[nome] = _ARGUMENTO_FICTICIO[chave]
    return kwargs


def _rotas(resolver=None, namespace="", kwargs=None):
    """Percorre o URLconf e devolve (nome, kwargs) das rotas nomeadas, com ou sem parâmetros."""
    resolver = resolver or get_resolver()
    kwargs = kwargs or {}
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            ns = f"{namespace}{p.namespace}:" if p.namespace else namespace
            yield from _rotas(p, ns, {**kwargs, **_argumentos_ficticios(p.pattern)})
        elif isinstance(p, URLPattern) and p.name:
            yield f"{namespace}{p.name}", {**kwargs, **_argumentos_ficticios(p.pattern)}


# --- NF014: nada responde sem autenticação -------------------------------------------


@pytest.mark.django_db
def test_toda_rota_do_web_exige_login_exceto_as_publicas(client):
    rotas = [(n, k) for n, k in _rotas() if n.startswith("web:")]
    assert rotas, "nenhuma rota encontrada"
    for nome, kwargs in rotas:
        resposta = client.get(reverse(nome, kwargs=kwargs))
        if nome in ROTAS_PUBLICAS:
            assert resposta.status_code == 200, nome
        elif nome == "web:logout":
            # POST-only: sem login o GET nunca mostra nada (405), e não é redirecionado ao login
            assert resposta.status_code == 405, nome
        else:
            # sem login: redireciona ao login (302); rota de objeto inexistente pode dar 404
            assert resposta.status_code in (302, 404), nome
            if resposta.status_code == 302:
                assert resposta["Location"].startswith(reverse("web:login")), nome


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.urls_acesso")
def test_varredura_cobre_rotas_com_parametros_e_nominais_exigem_login(client):
    rotas = {n: k for n, k in _rotas() if n.startswith("ficha_") and k}
    assert set(rotas) == {"ficha_int", "ficha_slug", "ficha_uuid", "ficha_path"}
    for nome, kwargs in rotas.items():
        assert kwargs, nome
        resposta = client.get(reverse(nome, kwargs=kwargs))
        assert resposta.status_code in (302, 404), nome
        if resposta.status_code == 302:
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


def test_login_com_senha_errada_mostra_o_erro_uma_unica_vez(client, diretor):
    resposta = client.post(reverse("web:login"), {"username": "diretor", "password": "errada"})
    corpo = resposta.content.decode()
    erro = resposta.context["form"].non_field_errors()[0]
    assert corpo.count(escape(erro)) == 1
    assert "Usuário ou senha inválidos" not in corpo


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


def test_logout_anonimo_nao_redireciona_para_o_login_com_next(client):
    resposta = client.post(reverse("web:logout"))
    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("web:login")
    assert "next=" not in resposta["Location"]


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
    corpo = client.get(reverse("web:inicio")).content.decode()
    assert "Membro de diretoria" in corpo
    assert "dados nominais" not in corpo
    client.logout()
    client.force_login(diretor)
    corpo = client.get(reverse("web:inicio")).content.decode()
    assert "Diretor" in corpo
    assert "dados nominais" in corpo
