"""Geração dos alertas de frequência (RF014) e de desempenho (RF015) (#24, #25, #26).

Os alertas são indicativos (RN012, NF022): nenhum efeito automático sobre o aluno. Cada um
guarda a regra e o limiar que o geraram, o tipo, a área e um motivo em linguagem simples
(NF004, NF021). As regras são as de `inteligencia.indicadores`; os limiares vêm da regra
ativa no banco (`inteligencia.regras.vigente`).

- Frequência, por semana (segunda a domingo): faltas não justificadas em dias letivos
  (RN001, RN002, RN005) >= limiar.
- Desempenho, por ciclo: queda da nota total (média das quatro áreas) ou de alguma área em
  relação ao último simulado em que o aluno foi avaliado (RN008) <= -limiar. Quem faltou não
  é avaliado (RN009); no primeiro simulado não há base de comparação.

Regerar é idempotente: no máximo um alerta de cada tipo por aluno e semana (NF005), atualizado
no lugar; o que deixou de valer fica inativo (NF007).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from core.models import Alerta, CicloCalendario, ResultadoSimulado
from inteligencia.models import RegraAlerta

from . import consultas
from . import indicadores as ind
from .regras import vigente

NOMES_AREA = dict(ResultadoSimulado.Area.choices)


@dataclass
class Geracao:
    novos: int = 0
    atualizados: int = 0
    desativados: int = 0
    mantidos: int = 0
    sem_regra: bool = False


def segunda(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def _numero(valor) -> str:
    return f"{valor:.1f}".replace(".", ",").replace(",0", "")


def _aplicar(geracao, existentes, desejados, criar):
    """Cria, atualiza ou desativa: `desejados` mapeia a chave do alerta a (motivo, extras)."""
    agora = timezone.now()
    for k, (motivo, extras) in desejados.items():
        alerta = existentes.pop(k, None)
        if alerta is None:
            criar(k, motivo, extras, agora)
            geracao.novos += 1
        elif (
            alerta.motivo != motivo
            or not alerta.ativo
            or any(getattr(alerta, c) != v for c, v in extras.items())
        ):
            alerta.motivo, alerta.ativo, alerta.data_geracao = motivo, True, agora
            for campo, valor in extras.items():
                setattr(alerta, campo, valor)
            alerta.save()
            geracao.atualizados += 1
        else:
            geracao.mantidos += 1
    for alerta in existentes.values():
        if alerta.ativo:
            alerta.ativo = False
            alerta.save(update_fields=["ativo"])
            geracao.desativados += 1


@transaction.atomic
def gerar_frequencia(semana: date, ano: int) -> Geracao:
    """Alertas de frequência da semana que começa na segunda `semana` (RF014)."""
    semana = segunda(semana)
    geracao = Geracao()
    regra = vigente(RegraAlerta.Tipo.FREQUENCIA)
    if regra is None:
        geracao.sem_regra = True
        return geracao
    domingo = semana + timedelta(days=6)
    alunos = list(consultas.alunos_do_ano(ano, ate=domingo))
    frequencias = consultas.frequencias(alunos, semana, domingo)
    desejados = {}
    for aluno in alunos:
        f = frequencias[aluno.pk]
        if f.faltas >= regra.limiar:
            motivo = (
                f"{f.faltas} falta(s) não justificada(s) na semana de {semana:%d/%m} a "
                f"{domingo:%d/%m/%Y}, em {f.dias} dia(s) letivo(s) (limiar: "
                f"{_numero(regra.limiar)} faltas)."
            )
            desejados[aluno.pk] = (motivo, {"regra": regra})
    existentes = {
        a.aluno_id: a
        for a in Alerta.objects.filter(tipo=Alerta.Tipo.FREQUENCIA, semana=semana, aluno__in=alunos)
    }

    def criar(matricula, motivo, extras, agora):
        Alerta.objects.create(
            aluno_id=matricula,
            tipo=Alerta.Tipo.FREQUENCIA,
            semana=semana,
            motivo=motivo,
            data_geracao=agora,
            **extras,
        )

    _aplicar(geracao, existentes, desejados, criar)
    return geracao


def _queda(historico, ciclo_id, limiar):
    """`(área ou "", motivo)` da queda do aluno no ciclo, ou None (RN008, RN009)."""
    quedas = []
    total = ind.delta(ind.serie(historico), ciclo_id)
    if total is not None and ind.classificar(total.valor, limiar) == ind.QUEDA:
        quedas.append(("", total))
    for area in ind.AREAS:
        d = ind.delta(ind.serie(historico, area), ciclo_id)
        if d is not None and ind.classificar(d.valor, limiar) == ind.QUEDA:
            quedas.append((area, d))
    if not quedas:
        return None
    partes = []
    for area, d in quedas:
        nome = "Média das quatro áreas" if not area else NOMES_AREA[area]
        partes.append(f"{nome}: {_numero(d.anterior)} → {_numero(d.atual)} ({_numero(d.valor)})")
    principal = quedas[0][0] if quedas[0][0] == "" else min(quedas, key=lambda q: q[1].valor)[0]
    motivo = (
        "Nota TRI caiu em relação ao último simulado em que o aluno foi avaliado. "
        + "; ".join(partes)
        + f" (limiar: queda de {_numero(limiar)} pontos)."
    )
    return principal, motivo


@transaction.atomic
def gerar_desempenho(ciclo: CicloCalendario) -> Geracao:
    """Alertas de queda de desempenho do ciclo (RF015)."""
    geracao = Geracao()
    regra = vigente(RegraAlerta.Tipo.DESEMPENHO)
    if regra is None:
        geracao.sem_regra = True
        return geracao
    alunos = list(consultas.alunos_do_ano(ciclo.data_inicio.year))
    historicos = consultas.historicos(alunos)
    desejados = {}
    for aluno in alunos:
        historico = historicos.get(aluno.pk)
        if not historico:
            continue
        queda = _queda(historico, ciclo.pk, regra.limiar)
        if queda:
            area, motivo = queda
            desejados[aluno.pk] = (motivo, {"regra": regra, "area": area})
    existentes = {
        a.aluno_id: a
        for a in Alerta.objects.filter(tipo=Alerta.Tipo.DESEMPENHO, ciclo=ciclo, aluno__in=alunos)
    }

    def criar(matricula, motivo, extras, agora):
        Alerta.objects.create(
            aluno_id=matricula,
            tipo=Alerta.Tipo.DESEMPENHO,
            ciclo=ciclo,
            motivo=motivo,
            data_geracao=agora,
            **extras,
        )

    _aplicar(geracao, existentes, desejados, criar)
    return geracao


def gerar_frequencia_periodo(inicio: date, fim: date, ano: int) -> Geracao:
    """Regera as semanas de `inicio` a `fim` (por exemplo, as de uma grade importada)."""
    total = Geracao()
    semana = segunda(inicio)
    while semana <= fim:
        parcial = gerar_frequencia(semana, ano)
        total.novos += parcial.novos
        total.atualizados += parcial.atualizados
        total.desativados += parcial.desativados
        total.mantidos += parcial.mantidos
        total.sem_regra = total.sem_regra or parcial.sem_regra
        semana += timedelta(days=7)
    return total


def gerar_desempenho_ano(ano: int) -> Geracao:
    """Regera todos os ciclos do ano com resultados: um ciclo importado muda o delta do
    seguinte (RN008)."""
    total = Geracao()
    ciclos = CicloCalendario.objects.filter(data_inicio__year=ano, simulados__isnull=False)
    for ciclo in ciclos.distinct().order_by("data_inicio"):
        parcial = gerar_desempenho(ciclo)
        total.novos += parcial.novos
        total.atualizados += parcial.atualizados
        total.desativados += parcial.desativados
        total.mantidos += parcial.mantidos
        total.sem_regra = total.sem_regra or parcial.sem_regra
    return total


def gerar_ano(ano: int) -> tuple[Geracao, Geracao]:
    """Regera os alertas de frequência de todas as semanas com registros do ano e os de
    desempenho de todos os ciclos com resultados."""
    from django.db.models import Max, Min

    from core.models import RegistroFrequencia

    limites = RegistroFrequencia.objects.filter(data__year=ano).aggregate(
        i=Min("data"), f=Max("data")
    )
    frequencia = (
        gerar_frequencia_periodo(limites["i"], limites["f"], ano) if limites["i"] else Geracao()
    )
    return frequencia, gerar_desempenho_ano(ano)


def apos_pendencias(pendencias) -> None:
    """Associar pendências muda frequência ou notas: regera o que elas afetam."""
    for pendencia in pendencias:
        if pendencia.origem == "FREQUENCIA":
            datas = sorted(date.fromisoformat(d) for d in pendencia.dados.get("codigos", {}))
            if datas:
                gerar_frequencia_periodo(datas[0], datas[-1], pendencia.ano)
        elif pendencia.origem == "SIMULADO":
            gerar_desempenho_ano(pendencia.ano)


def simular_frequencia(semanas: tuple[date, date] | None, ano: int, limiar) -> int:
    """Quantos alunos teriam alerta de frequência em alguma das `semanas` com o `limiar`
    (pré-visualização do RF018). Não grava nada."""
    if semanas is None:
        return 0
    sinalizados = set()
    semana = segunda(semanas[0])
    while semana <= semanas[1]:
        domingo = semana + timedelta(days=6)
        alunos = list(consultas.alunos_do_ano(ano, ate=domingo))
        for matricula, f in consultas.frequencias(alunos, semana, domingo).items():
            if f.faltas >= limiar:
                sinalizados.add(matricula)
        semana += timedelta(days=7)
    return len(sinalizados)


def simular_desempenho(ciclo: CicloCalendario | None, limiar) -> int:
    """Quantos alunos teriam alerta de queda no `ciclo` com o `limiar` (RF018). Não grava."""
    if ciclo is None:
        return 0
    alunos = list(consultas.alunos_do_ano(ciclo.data_inicio.year))
    historicos = consultas.historicos(alunos)
    return sum(
        1 for a in alunos if historicos.get(a.pk) and _queda(historicos[a.pk], ciclo.pk, limiar)
    )
