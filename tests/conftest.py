"""Fixtures compartilhadas. Dados sempre sintéticos."""

import pytest
from django.contrib.auth import get_user_model

from core.models import Turma

SENHA = "senha-sintetica-123"  # nosec: dado de teste, sem relação com contas reais


@pytest.fixture(autouse=True)
def _suite_por_http(settings):
    """A suíte fala HTTP puro; sem isto, o padrão de produção responderia 301 em tudo.
    Os testes do modo HTTPS ligam `SECURE_SSL_REDIRECT` por conta própria."""
    settings.SECURE_SSL_REDIRECT = False


@pytest.fixture
def diretor(db):
    return get_user_model().objects.create_user(
        "diretor", "diretor@exemplo.org", SENHA, perfil="DIRETOR"
    )


@pytest.fixture
def membro(db):
    return get_user_model().objects.create_user("membro", "membro@exemplo.org", SENHA)


@pytest.fixture
def cliente_diretor(client, diretor):
    client.force_login(diretor)
    return client


@pytest.fixture
def turma_a(db):
    return Turma.objects.create(nome="Turma A", ano=2026)


def importar_em_dois_passos(cliente, url, montar):
    """Conferir e confirmar, como a tela exige. `montar(acao)` devolve o POST completo, com
    um arquivo novo a cada chamada. Devolve a resposta da confirmação."""
    conferencia = cliente.post(url, montar("conferir"))
    token = conferencia.context["resultado"].token
    assert token, "a conferência não emitiu token"
    return cliente.post(url, {**montar("importar"), "token": token})
