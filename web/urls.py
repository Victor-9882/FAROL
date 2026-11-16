from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", views.Login.as_view(), name="login"),
    path("sair/", views.Logout.as_view(), name="logout"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/novo/", views.usuario_novo, name="usuario_novo"),
    path("usuarios/<int:pk>/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/link-senha/", views.usuario_link_senha, name="usuario_link_senha"),
    path("definir-senha/<uidb64>/<token>/", views.DefinirSenha.as_view(), name="definir_senha"),
    path("saude/", views.saude, name="saude"),
]
