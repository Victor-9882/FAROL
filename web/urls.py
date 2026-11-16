from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", views.Login.as_view(), name="login"),
    path("sair/", views.Logout.as_view(), name="logout"),
    path("saude/", views.saude, name="saude"),
]
