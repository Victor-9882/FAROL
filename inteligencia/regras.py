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


def descricao_para(tipo: str, limiar: Decimal, caminho: Path = ARQUIVO_PADRAO) -> str:
    """Descrição da regra para um limiar, a partir do texto de `regras_padrao.yaml`."""
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    modelo = str(dados.get(tipo, {}).get("descricao", "Limiar: {limiar}."))
    return modelo.format(limiar=_numero(Decimal(limiar)))


def alterar_limiar(tipo: str, limiar: Decimal, *, autor):
    """Troca o limiar da regra do tipo (RF018): desativa a regra vigente e cria outra, para os
    alertas antigos continuarem apontando para o limiar que os gerou. Audita quem, quando e o
    valor anterior (NF009). Devolve a regra vigente (a mesma, se o limiar não mudou)."""
    from django.db import transaction

    from core.auditoria import registrar_alteracoes
    from core.models import RegistroAlteracao

    from .models import RegraAlerta

    limiar = Decimal(limiar).quantize(Decimal("0.01"))  # como no campo (2 casas)
    with transaction.atomic():
        anterior = vigente(tipo)
        if anterior is not None and anterior.limiar == limiar:
            return anterior
        if anterior is not None:
            anterior.ativa = False
            anterior.save(update_fields=["ativa"])
            registrar_alteracoes(autor=autor, objeto=anterior, anteriores={"ativa": True})
        nova = RegraAlerta.objects.create(
            tipo_regra=tipo, limiar=limiar, descricao=descricao_para(tipo, limiar), ativa=True
        )
        RegistroAlteracao.objects.create(
            autor=autor,
            modelo=nova._meta.label_lower,
            objeto_id=str(nova.pk),
            campo="limiar",
            valor_anterior="" if anterior is None else str(anterior.limiar),
            valor_novo=str(nova.limiar),
        )
    return nova
