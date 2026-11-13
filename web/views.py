"""Views da camada de Apresentação."""

from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator


@login_not_required
def saude(request):
    """Verificação de saúde: confirma que a aplicação está no ar e alcança o banco.

    Pública de propósito: não expõe dado de aluno.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


@method_decorator(login_not_required, name="dispatch")
class Login(LoginView):
    """Tela de login (RF001)."""

    template_name = "web/login.html"
    redirect_authenticated_user = True


class Logout(LogoutView):
    """Encerra a sessão. Só aceita POST, para que um link externo não deslogue ninguém."""

    next_page = reverse_lazy("web:login")


def inicio(request):
    """Página inicial. O painel (RF010) vem em issue própria; aqui só confirma o perfil."""
    return render(request, "web/inicio.html")
