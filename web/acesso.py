"""Controle de acesso por perfil (RF001, RN013, NF013, NF014).

A autenticação é exigida em todo o site pelo `LoginRequiredMiddleware` (negar por padrão).
Rotas públicas precisam de `@login_not_required`. Rotas com dado nominal (nome, matrícula)
usam `@diretor_required`: o Membro recebe 403 mesmo por URL direta.
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, resolve_url
from django.urls import reverse


def diretor_required(view):
    """Restringe a view ao perfil Diretor; autenticação já é garantida pelo middleware."""

    @wraps(view)
    def envolvida(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_diretor:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return envolvida


@login_not_required
def entrada_do_admin(request):
    """Substitui o formulário de `/admin/login/` pela tela única de entrada (RF001, NF013).

    Anônimo vai para `/entrar/` levando o `next`; a validação do `next` fica com o `LoginView`.
    Staff autenticado vai ao índice do admin. Autenticado sem `is_staff` recebe 403: redirecioná-lo
    a `/entrar/` criaria laço, porque o `Login` redireciona quem já está autenticado.
    Esta view nunca autentica, nem por POST.
    """
    if not request.user.is_authenticated:
        destino = request.GET.get(REDIRECT_FIELD_NAME) or reverse("admin:index")
        return redirect_to_login(destino, resolve_url(settings.LOGIN_URL))
    if request.user.is_active and request.user.is_staff:
        return redirect("admin:index")
    raise PermissionDenied
