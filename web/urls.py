from django.urls import path

from . import cadastro, calendario, views

app_name = "web"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", views.Login.as_view(), name="login"),
    path("sair/", views.Logout.as_view(), name="logout"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/novo/", views.usuario_novo, name="usuario_novo"),
    path("usuarios/<int:pk>/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/link-senha/", views.usuario_link_senha, name="usuario_link_senha"),
    path("alunos/", cadastro.alunos, name="alunos"),
    path("alunos/novo/", cadastro.aluno_novo, name="aluno_novo"),
    path("alunos/importar/", cadastro.cadastro_importar, name="cadastro_importar"),
    path("alunos/importar/modelo.xlsx", cadastro.cadastro_modelo_xlsx, name="cadastro_modelo_xlsx"),
    path("alunos/importar/modelo.csv", cadastro.cadastro_modelo_csv, name="cadastro_modelo_csv"),
    path("alunos/<str:matricula>/editar/", cadastro.aluno_editar, name="aluno_editar"),
    path("importacoes/", cadastro.importacoes, name="importacoes"),
    path("turmas/", cadastro.turmas, name="turmas"),
    path("turmas/nova/", cadastro.turma_nova, name="turma_nova"),
    path("turmas/<int:pk>/", cadastro.turma_detalhe, name="turma_detalhe"),
    path("turmas/<int:pk>/editar/", cadastro.turma_editar, name="turma_editar"),
    path("calendario/", calendario.calendario, name="calendario"),
    path("calendario/importar/", calendario.calendario_importar, name="calendario_importar"),
    path(
        "calendario/importar/modelo/<slug:tipo>/<slug:formato>/",
        calendario.calendario_modelo,
        name="calendario_modelo",
    ),
    path("calendario/<slug:tipo>/novo/", calendario.calendario_item, name="calendario_item_novo"),
    path("calendario/<slug:tipo>/<int:pk>/", calendario.calendario_item, name="calendario_item"),
    path("definir-senha/<uidb64>/<token>/", views.DefinirSenha.as_view(), name="definir_senha"),
    path("saude/", views.saude, name="saude"),
]
