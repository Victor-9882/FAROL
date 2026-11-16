"""Regras de alerta vigentes e seus valores padrão (RF018, NF021, IC-10).

Os valores padrão ficam em `config/regras_padrao.yaml` e só entram na primeira carga (migração
de dados `inteligencia.0002`). Depois disso, os limiares vivem no banco (`RegraAlerta`).
"""

from decimal import Decimal
from pathlib import Path

import yaml

ARQUIVO_PADRAO = Path(__file__).resolve().parent.parent / "config" / "regras_padrao.yaml"


def padroes(caminho: Path = ARQUIVO_PADRAO) -> dict[str, dict]:
    """`{tipo: {"limiar": Decimal, "descricao": str}}` do arquivo de valores padrão."""
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    regras = {}
    for tipo, valores in dados.items():
        limiar = Decimal(str(valores["limiar"]))
        descricao = str(valores["descricao"]).format(limiar=_numero(limiar))
        regras[tipo] = {"limiar": limiar, "descricao": descricao}
    return regras


def _numero(valor: Decimal) -> str:
    """3 em vez de 3.00; 30 em vez de 3E+1."""
    return format(valor.normalize(), "f")


def criar_padroes(RegraAlerta, caminho: Path = ARQUIVO_PADRAO) -> int:  # noqa: N803
    """Cria a regra padrão de cada tipo que ainda não tem regra ativa. Devolve quantas."""
    criadas = 0
    for tipo, valores in padroes(caminho).items():
        if not RegraAlerta.objects.filter(tipo_regra=tipo, ativa=True).exists():
            RegraAlerta.objects.create(tipo_regra=tipo, ativa=True, **valores)
            criadas += 1
    return criadas


def vigente(tipo: str):
    """A regra ativa do tipo, ou None (sem regra, nenhum alerta desse tipo é gerado)."""
    from .models import RegraAlerta

    return RegraAlerta.objects.filter(tipo_regra=tipo, ativa=True).first()
