"""Faltas e justificativas de um aluno (RF008, RN002, RN013, NF009).

Só o Diretor: a tela traz nome e matrícula e grava. Mensagens genéricas, sem nome nem matrícula.
Depois de mudar, a view regenera o alerta de frequência da semana (a regra mora em `ingestao/`,
que não importa `inteligencia`).
"""

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from core.models import Aluno, RegistroFrequencia
from ingestao import justificativas
from inteligencia import alertas

from .acesso import diretor_required

ACOES = {
    "justificar": (justificativas.justificar, "Falta justificada."),
    "retirar": (justificativas.retirar_justificativa, "Justificativa retirada."),
}


@diretor_required
@require_http_methods(["GET", "POST"])
def faltas(request, matricula):
    aluno = get_object_or_404(Aluno.objects.select_related("turma"), pk=matricula)
    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao not in ACOES:
            return HttpResponseBadRequest("Ação inválida.")
        try:
            pk = int(request.POST.get("registro", ""))
        except ValueError:
            return HttpResponseBadRequest("Registro inválido.")
        registro = get_object_or_404(RegistroFrequencia, pk=pk, aluno=aluno)
        servico, mensagem = ACOES[acao]
        try:
            with transaction.atomic():
                mudou = servico(registro, autor=request.user)
                if mudou:
                    alertas.gerar_frequencia(registro.data, aluno.turma.ano)
        except justificativas.JustificativaRecusada as erro:
            messages.error(request, f"Não foi possível: {erro}.")
        else:
            messages.success(request, mensagem if mudou else "Nada a alterar.")
        return redirect("web:faltas", matricula=aluno.matricula)
    return render(
        request,
        "web/faltas.html",
        {"aluno": aluno, "faltas": justificativas.faltas_do_aluno(aluno)},
    )
