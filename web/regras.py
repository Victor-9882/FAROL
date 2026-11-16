"""Regras de alerta e seus limiares (RF018, NF009, NF021).

Todos os usuários veem as regras em linguagem simples (NF021); só o Diretor altera o limiar.
Salvar exige ter pré-visualizado o mesmo valor: a tela mostra antes quantos alunos seriam
sinalizados com o limiar atual e com o novo. A troca fica auditada (autor, data, valor
anterior) e os alertas do ano são regerados com o novo limiar.
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from core.auditoria import historico_de
from inteligencia import alertas, painel, regras
from inteligencia.models import RegraAlerta

from .acesso import diretor_required

# Tipos editáveis e a faixa de valores aceita (frequência: faltas na semana; desempenho: pontos).
FAIXAS = {
    RegraAlerta.Tipo.FREQUENCIA: (Decimal(1), Decimal(7), "faltas não justificadas na semana"),
    RegraAlerta.Tipo.DESEMPENHO: (Decimal(1), Decimal(500), "pontos de queda na nota TRI"),
}


def lista(request):
    ativas = {r.tipo_regra: r for r in RegraAlerta.objects.filter(ativa=True)}
    historico = RegraAlerta.objects.filter(ativa=False).order_by("-criado_em")
    contexto = {
        "regras": [(tipo, ativas.get(tipo), FAIXAS[tipo][2]) for tipo in FAIXAS],
        "historico": historico,
        "rotulos": dict(RegraAlerta.Tipo.choices),
    }
    return render(request, "web/regras.html", contexto)


def _limiar(texto, tipo):
    minimo, maximo, _ = FAIXAS[tipo]
    try:
        valor = Decimal(str(texto).strip().replace(",", "."))
    except InvalidOperation:
        return None, "Informe um número."
    if not valor.is_finite() or not minimo <= valor <= maximo:
        return None, f"O limiar precisa estar entre {minimo} e {maximo}."
    if tipo == RegraAlerta.Tipo.FREQUENCIA and valor != valor.to_integral_value():
        return None, "O limiar de frequência é um número inteiro de faltas."
    return valor.quantize(Decimal("0.01")), ""


def _previa(tipo, limiar, ref):
    if tipo == RegraAlerta.Tipo.FREQUENCIA:
        return alertas.simular_frequencia(ref.semanas_alerta, ref.ano, limiar)
    return alertas.simular_desempenho(ref.ciclo, limiar)


@diretor_required
def editar(request, tipo):
    if tipo not in FAIXAS:
        raise Http404
    atual = regras.vigente(tipo)
    ref = painel.referencia()
    contexto = {
        "tipo": tipo,
        "rotulo": dict(RegraAlerta.Tipo.choices)[tipo],
        "unidade": FAIXAS[tipo][2],
        "atual": atual,
        "ref": ref,
        "historico": historico_de(atual) if atual else [],
        "valor": request.POST.get("limiar", "") if request.method == "POST" else "",
    }
    if atual is not None:
        contexto["previa_atual"] = _previa(tipo, atual.limiar, ref)
    if request.method == "POST":
        limiar, erro = _limiar(request.POST.get("limiar", ""), tipo)
        if erro:
            contexto["erro"] = erro
        elif request.POST.get("acao") == "salvar" and request.POST.get("previsto") == str(limiar):
            nova = regras.alterar_limiar(tipo, limiar, autor=request.user)
            alertas.gerar_ano(ref.ano)
            messages.success(
                request,
                f"Limiar de {contexto['rotulo'].lower()} agora é {regras._numero(nova.limiar)}; "
                "alertas recalculados.",
            )
            return redirect("web:regras")
        else:
            contexto["limiar"] = limiar
            contexto["previa"] = _previa(tipo, limiar, ref)
            contexto["descricao"] = regras.descricao_para(tipo, limiar)
    return render(request, "web/regra_form.html", contexto)
