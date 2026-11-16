"""URLconf só de teste: rotas nominais fictícias protegidas pelo decorador de perfil."""

from django.http import JsonResponse
from django.urls import include, path

from web.acesso import diretor_required


@diretor_required
def ficha_nominal(request):
    return JsonResponse({"nome": "Aluno Sintético", "matricula": "S0001"})


@diretor_required
def ficha_com_parametros(request, **kwargs):
    return JsonResponse({"nome": "Aluno Sintético", "matricula": "S0001"})


urlpatterns = [
    path("nominal/ficha/", ficha_nominal, name="ficha_nominal"),
    path("nominal/<int:pk>/", ficha_com_parametros, name="ficha_int"),
    path("nominal/<slug:turma>/<str:nome>/", ficha_com_parametros, name="ficha_slug"),
    path("nominal/<uuid:codigo>/", ficha_com_parametros, name="ficha_uuid"),
    path("nominal/arquivo/<path:caminho>", ficha_com_parametros, name="ficha_path"),
    path("", include("web.urls")),
]
