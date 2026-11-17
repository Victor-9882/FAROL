"""Filtros de template do FAROL."""

from django import template

register = template.Library()


@register.filter
def dictkey(dicionario, chave):
    """`{{ d|dictkey:"chave" }}`: acesso a dicionário por chave variável."""
    return dicionario.get(chave, []) if hasattr(dicionario, "get") else []


@register.filter
def indice(valor):
    """Índice de −1 a +1 com sinal e duas casas: `+0,42`, `−1,00`, `0,00`; `—` sem valor."""
    if valor is None:
        return "—"
    texto = f"{abs(valor):.2f}".replace(".", ",")
    return f"+{texto}" if valor > 0.004 else f"−{texto}" if valor < -0.004 else "0,00"


@register.filter
def pontos(valor):
    """Δ em pontos com sinal e uma casa: `+12,5`, `−60`; `—` sem valor."""
    if valor is None:
        return "—"
    texto = f"{abs(valor):.1f}".replace(".", ",").removesuffix(",0")
    return f"+{texto}" if valor > 0 else f"−{texto}" if valor < 0 else "0"


@register.filter
def medidor(valor):
    """Posição de um índice de −1 a +1 numa barra de 0 a 100%: `(início, largura)` a partir
    do meio, para o medidor da ficha. Texto com ponto decimal, porque vai para o CSS e o
    template localizaria um número (vírgula)."""
    if valor is None:
        return ("50", "0")
    fim = 50 + 50 * max(-1.0, min(1.0, valor))
    return (f"{min(50, fim):.1f}", f"{abs(fim - 50):.1f}")
