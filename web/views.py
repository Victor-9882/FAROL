"""Views da camada de Apresentação."""

from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetConfirmView
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_POST

from core.auditoria import historico_de
from core.models import RegistroAlteracao, Usuario

from .acesso import diretor_required
from .forms import UsuarioEdicaoForm, UsuarioNovoForm


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


@method_decorator(login_not_required, name="dispatch")
class Logout(LogoutView):
    """Encerra a sessão. Só aceita POST, para que um link externo não deslogue ninguém.

    Pública de propósito: um POST anônimo (sessão já expirada) deve só voltar ao login,
    sem passar pelo `login_required` global. O destino vem de LOGOUT_REDIRECT_URL.
    """


# --- Gestão de usuários (RF002, NF009) -----------------------------------------------


def _gerenciaveis():
    """Superusuários são geridos só no admin do Django e ficam fora destas telas."""
    return Usuario.objects.filter(is_superuser=False)


@diretor_required
def usuarios(request):
    return render(request, "web/usuarios.html", {"usuarios": _gerenciaveis().order_by("username")})


@diretor_required
def usuario_novo(request):
    form = UsuarioNovoForm(request.POST or None, autor=request.user)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        return redirect("web:usuario_editar", pk=usuario.pk)
    return render(request, "web/usuario_form.html", {"form": form, "alvo": None})


@diretor_required
def usuario_editar(request, pk):
    alvo = get_object_or_404(_gerenciaveis(), pk=pk)
    form = UsuarioEdicaoForm(request.POST or None, instance=alvo, autor=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        request.user.refresh_from_db()
        return redirect("web:usuarios" if request.user.is_diretor else "web:inicio")
    contexto = {"form": form, "alvo": alvo, "historico": historico_de(alvo)}
    return render(request, "web/usuario_form.html", contexto)


@diretor_required
@require_POST
def usuario_link_senha(request, pk):
    """Gera link de uso único para o usuário definir a senha; o Diretor o repassa por fora."""
    alvo = get_object_or_404(_gerenciaveis(), pk=pk)
    # Quem gera o link não pode usá-lo para entrar como o alvo sem que ele perceba:
    # a senha anterior deixa de valer (NF009).
    invalidou = alvo.has_usable_password()
    if invalidou:
        alvo.set_unusable_password()
        alvo.save(update_fields=["password"])
    caminho = reverse(
        "web:definir_senha",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(alvo.pk)),
            "token": default_token_generator.make_token(alvo),
        },
    )
    RegistroAlteracao.objects.create(
        autor=request.user,
        modelo=alvo._meta.label_lower,
        objeto_id=str(alvo.pk),
        campo="senha",
        valor_anterior="",
        valor_novo="link de definição gerado"
        + ("; senha anterior invalidada" if invalidou else ""),
    )
    contexto = {"alvo": alvo, "link": request.build_absolute_uri(caminho)}
    return render(request, "web/usuario_link.html", contexto)


@method_decorator(login_not_required, name="dispatch")
class DefinirSenha(PasswordResetConfirmView):
    """Definição de senha por link de uso único (token do Django, validade padrão)."""

    template_name = "web/definir_senha.html"
    success_url = reverse_lazy("web:login")
