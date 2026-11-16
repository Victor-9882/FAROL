"""Base comum das importações: triagem, totais e isolamento por linha (NF006, NF008, NF025)."""

from datetime import date
from pathlib import Path

import pytest
from django.db import transaction

from core.models import Turma
from ingestao.base import (
    ResumoImportacao,
    linha_isolada,
    transacao_de_importacao,
    triar,
)
from ingestao.cadastro import COLUNAS, importar_cadastro
from ingestao.calendario import TIPOS
from ingestao.leitura import ler_tabela

pytestmark = pytest.mark.django_db

PASTA = Path(__file__).parent / "dados_sinteticos" / "pequena" / "2026"


def _ler(nome, colunas, opcionais=frozenset()):
    with (PASTA / nome).open("rb") as f:
        return ler_tabela(f, nome, colunas=colunas, opcionais=opcionais)


def test_triar_isola_invalida_e_repetida_sem_interromper():
    linhas = [{"k": "a", "_linha": 2}, {"k": "", "_linha": 3}, {"k": "a", "_linha": 4}]
    linhas.append({"k": "b", "_linha": 5})
    recusadas = []

    def validar(linha):
        return ({"k": linha["k"]}, "") if linha["k"] else (None, "vazia")

    validas = triar(
        linhas,
        validar,
        chave=lambda d: d["k"],
        recusar=lambda linha, motivo: recusadas.append((linha["_linha"], motivo)),
    )
    assert [n for n, _ in validas] == [2, 5]
    assert recusadas == [(3, "vazia"), (4, "registro repetido no arquivo")]


def test_total_linhas_fecha_com_o_arquivo(diretor):
    linhas = _ler("cadastro_alunos.csv", COLUNAS)
    resumo = importar_cadastro(
        linhas, ano=2026, autor=diretor, data_mudanca=date(2026, 3, 2), gravar=True
    )
    assert resumo.total_linhas == len(linhas)
    # reimportar: tudo sem alteração, e continua fechando
    outra = importar_cadastro(
        linhas, ano=2026, autor=diretor, data_mudanca=date(2026, 3, 2), gravar=True
    )
    assert outra.total_linhas == len(linhas) and outra.sem_alteracao == len(linhas)

    tipo = TIPOS["dias"]
    dias = _ler("calendario_letivo.csv", tipo.colunas, tipo.opcionais)
    resumo = tipo.importar(dias, ano=2026, autor=diretor, gravar=True)
    assert resumo.total_linhas == len(dias)


def test_importados_e_divergentes_do_cadastro(diretor):
    def linha(matricula, nome, turma, n):
        return {
            "matricula": matricula,
            "nome": nome,
            "turma": turma,
            "data_ingresso": "02/02/2026",
            "_linha": n,
        }

    kw = {"ano": 2026, "autor": diretor, "data_mudanca": date(2026, 3, 2), "gravar": True}
    importar_cadastro(
        [linha("S260001", "Ana", "Turma A", 2), linha("S260002", "Bia", "Turma A", 3)], **kw
    )
    resumo = importar_cadastro(
        [
            linha("S260001", "Ana", "Turma B", 2),  # mudança de turma
            linha("S260002", "Outra Pessoa", "Turma A", 3),  # divergência
            linha("S260003", "Cris", "Turma A", 4),  # criado
        ],
        **kw,
    )
    assert resumo.mudancas_turma == 1 and len(resumo.divergencias) == 1
    assert resumo.importados == 2  # criado + mudança de turma
    assert resumo.ignorados == 0  # divergência não é ignorado
    assert resumo.divergentes == 1
    assert resumo.total_linhas == 3
    assert resumo.assinatura() == [2, 0, 0, 0]


def test_transacao_sem_gravar_desfaz():
    with transacao_de_importacao(gravar=False):
        Turma.objects.create(nome="Turma X", ano=2026)
    assert not Turma.objects.exists()
    with transacao_de_importacao(gravar=True):
        Turma.objects.create(nome="Turma X", ano=2026)
    assert Turma.objects.count() == 1


def test_linha_isolada_restricao_do_banco_nao_aborta():
    Turma.objects.create(nome="Turma A", ano=2026)
    motivos = []
    with transaction.atomic():
        for nome in ("Turma A", "Turma B"):
            with linha_isolada(motivos.append):
                Turma.objects.create(nome=nome, ano=2026)
    assert motivos == ["registro recusado por uma restrição do banco"]
    assert set(Turma.objects.values_list("nome", flat=True)) == {"Turma A", "Turma B"}


def test_resumo_vazio_fecha():
    assert ResumoImportacao().total_linhas == 0


def test_linha_isolada_validacao_nao_vaza_valor():
    from django.core.exceptions import ValidationError

    motivos = []
    erro = ValidationError({"nome": ["valor-secreto"], "ano": ["x"], "__all__": ["texto do clean"]})
    with linha_isolada(motivos.append):
        raise erro
    with linha_isolada(motivos.append):
        raise ValidationError("mensagem do modelo")
    assert motivos == ["campos inválidos: nome, ano; texto do clean", "mensagem do modelo"]
    assert "valor-secreto" not in " ".join(motivos)
