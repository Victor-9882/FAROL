"""Fixtures compartilhadas. Dados sempre sintéticos."""

import pytest
from django.contrib.auth import get_user_model

from core.models import Turma

SENHA = "senha-sintetica-123"  # nosec: dado de teste, sem relação com contas reais


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
