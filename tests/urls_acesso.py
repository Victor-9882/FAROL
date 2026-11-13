"""URLconf só de teste: rotas nominais fictícias protegidas pelo decorador de perfil."""

from django.http import JsonResponse
from django.urls import include, path

from web.acesso import diretor_required


@diretor_required
def ficha_nominal(request):
    return JsonResponse({"nome": "Aluno Sintético", "matricula": "S0001"})


urlpatterns = [
    path("nominal/ficha/", ficha_nominal, name="ficha_nominal"),
    path("", include("web.urls")),
]
