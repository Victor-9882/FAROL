"""Ficha longitudinal do aluno (RF011) com a comparação com o histórico e a turma (RF013).

Dado nominal: só o Diretor (RN013, NF013); o Membro recebe 403 mesmo por URL direta.
"""

from django.shortcuts import get_object_or_404, render

from core.models import Aluno
from inteligencia import ficha as dados_ficha

from . import graficos
from .acesso import diretor_required


@diretor_required
def ficha(request, matricula):
    aluno = get_object_or_404(Aluno.objects.select_related("turma"), pk=matricula)
    dados = dados_ficha.montar(aluno)
    avaliadas = dados["avaliadas"]
    rotulos = [f"C{linha.numero}" for linha in avaliadas]
    dados["grafico_notas"] = graficos.linhas(
        rotulos,
        {
            "Aluno (média das áreas)": [linha.total for linha in avaliadas],
            "Média da turma (referência)": [linha.media_turma for linha in avaliadas],
        },
        titulo="Nota TRI por ciclo",
    )
    dados["grafico_areas"] = graficos.linhas(
        rotulos,
        {nome: [linha.notas.get(area) for linha in avaliadas] for area, nome in dados["areas"]},
        titulo="Nota TRI por área",
    )
    com_dias = [linha for linha in dados["linhas"] if linha.frequencia.dias]
    dados["grafico_presenca"] = graficos.linhas(
        [f"C{linha.numero}" for linha in com_dias],
        {"Presença": [linha.frequencia.percentual for linha in com_dias]},
        titulo="Presença por ciclo (%)",
        unidade="%",
    )
    return render(request, "web/ficha.html", {"aluno": aluno, **dados})
