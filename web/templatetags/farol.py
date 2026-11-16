"""Filtros de template do FAROL."""

from django import template

register = template.Library()


@register.filter
def dictkey(dicionario, chave):
    """`{{ d|dictkey:"chave" }}`: acesso a dicionário por chave variável."""
    return dicionario.get(chave, []) if hasattr(dicionario, "get") else []
