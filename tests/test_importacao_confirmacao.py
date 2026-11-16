"""Token de confirmação da conferência: sem estado no servidor (NF006, NF008)."""

import pytest

from ingestao.confirmacao import (
    VALIDADE_SEGUNDOS,
    emitir_token,
    impressao_digital,
    token_confere,
)

BASE = {
    "usuario_id": 7,
    "arquivo": impressao_digital(b"conteudo sintetico"),
    "parametros": {"ano": 2026, "data_mudanca": "2026-03-02"},
    "resumo": [10, 2, 1, 0],
}


def test_token_confere():
    assert token_confere(emitir_token(**BASE), **BASE)


@pytest.mark.parametrize(
    "mudanca",
    [
        {"usuario_id": 8},
        {"arquivo": impressao_digital(b"conteudo sintetico.")},
        {"parametros": {"ano": 2027, "data_mudanca": "2026-03-02"}},
        {"resumo": [10, 2, 1, 1]},
    ],
)
def test_token_recusa_o_que_mudou(mudanca):
    assert not token_confere(emitir_token(**BASE), **{**BASE, **mudanca})


@pytest.mark.parametrize("token", ["", "lixo", None])
def test_token_invalido_nao_confere(token):
    assert not token_confere(token, **BASE)


def test_token_adulterado_nao_confere():
    token = emitir_token(**BASE)
    adulterado = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert not token_confere(adulterado, **BASE)


def test_token_nao_carrega_conteudo_do_arquivo():
    assert "conteudo" not in emitir_token(**BASE)


def test_token_validade_limite(monkeypatch):
    agora = 1_800_000_000.0  # inteiro: o carimbo do token é truncado em segundos
    monkeypatch.setattr("django.core.signing.time.time", lambda: agora)
    token = emitir_token(**BASE)
    monkeypatch.setattr("django.core.signing.time.time", lambda: agora + VALIDADE_SEGUNDOS)
    assert token_confere(token, **BASE)
    monkeypatch.setattr("django.core.signing.time.time", lambda: agora + VALIDADE_SEGUNDOS + 1)
    assert not token_confere(token, **BASE)
