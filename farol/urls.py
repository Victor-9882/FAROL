"""Rotas do FAROL."""

from django.contrib import admin
from django.urls import include, path

from web.acesso import entrada_do_admin

urlpatterns = [
    # Antes do admin: `/admin/login/` deixa de ser formulário e leva à tela única (issue #49).
    path("admin/login/", entrada_do_admin),
    path("admin/", admin.site.urls),
    path("", include("web.urls")),
]
