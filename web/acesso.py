"""Controle de acesso por perfil (RF001, RN013, NF013, NF014).

A autenticação é exigida em todo o site pelo `LoginRequiredMiddleware` (negar por padrão).
Rotas públicas precisam de `@login_not_required`. Rotas com dado nominal (nome, matrícula)
usam `@diretor_required`: o Membro recebe 403 mesmo por URL direta.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied


def diretor_required(view):
    """Restringe a view ao perfil Diretor; autenticação já é garantida pelo middleware."""

    @wraps(view)
    def envolvida(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_diretor:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return envolvida
