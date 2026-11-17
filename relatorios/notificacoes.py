"""E-mail de fechamento do ciclo (RF017).

Só números agregados e nomes de turma: nenhum campo de `Aluno` entra no assunto nem no corpo
(RN013, NF013). Os alertas são indicativos (RN012). A idempotência vem de `NotificacaoCiclo`.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings
from django.core import mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import Alerta, CicloCalendario, Usuario
from inteligencia import painel

from .models import NotificacaoCiclo


@dataclass
class LinhaTurma:
    turma: str
    alunos: int
    queda: int
    estagnado: int
    evolucao: int
    sem_avaliacao: int
    sem_presenca: int
    frequencia: str
    participacao: str


@dataclass
class ResumoCiclo:
    numero: int
    inicio: date
    fim: date
    total: LinhaTurma
    turmas: list[LinhaTurma] = field(default_factory=list)
    alertas_frequencia: int = 0
    alertas_desempenho: int = 0


def _fechados(hoje: date):
    return CicloCalendario.objects.filter(data_fim__lt=hoje, simulados__isnull=False).distinct()


def ciclo_a_notificar(hoje: date) -> CicloCalendario | None:
    """O ciclo fechado (`data_fim < hoje`, com resultados) mais recente, se ainda sem
    notificação. Ciclos anteriores nunca notificados são ignorados."""
    ciclo = _fechados(hoje).order_by("-data_inicio").first()
    if ciclo is None or NotificacaoCiclo.objects.filter(ciclo=ciclo).exists():
        return None
    return ciclo


def _percentual(valor) -> str:
    return "sem dados" if valor is None else f"{valor:.1f}%".replace(".", ",")


def _linha(s: painel.Situacao) -> LinhaTurma:
    return LinhaTurma(
        turma=s.turma,
        alunos=s.total_alunos,
        queda=s.contagem("queda"),
        estagnado=s.contagem("estagnado"),
        evolucao=s.contagem("evolucao"),
        sem_avaliacao=s.contagem("sem_avaliacao"),
        sem_presenca=s.contagem("inativos"),
        frequencia=_percentual(s.frequencia.percentual),
        participacao=_percentual(s.participacao.percentual),
    )


def resumo_do_ciclo(ciclo: CicloCalendario) -> ResumoCiclo:
    """Indicadores agregados do ciclo, sem objetos `Aluno`."""
    ano = ciclo.data_inicio.year
    numero = CicloCalendario.objects.filter(
        data_inicio__year=ano, data_inicio__lte=ciclo.data_inicio
    ).count()
    ref = painel.Referencia(ano=ano, ciclo=ciclo, numero_ciclo=numero)
    turmas, total = painel.situacao(ref)
    segunda = ciclo.data_inicio - timedelta(days=ciclo.data_inicio.weekday())
    ativos = Alerta.objects.filter(ativo=True, aluno__turma__ano=ano)
    return ResumoCiclo(
        numero=numero,
        inicio=ciclo.data_inicio,
        fim=ciclo.data_fim,
        total=_linha(total),
        turmas=[_linha(t) for t in turmas],
        alertas_frequencia=ativos.filter(
            tipo=Alerta.Tipo.FREQUENCIA, semana__gte=segunda, semana__lte=ciclo.data_fim
        ).count(),
        alertas_desempenho=ativos.filter(tipo=Alerta.Tipo.DESEMPENHO, ciclo=ciclo).count(),
    )


def destinatarios() -> list[str]:
    """Usuários ativos com e-mail, exceto superusuários (Diretor e Membro)."""
    return list(
        Usuario.objects.filter(is_active=True, is_superuser=False)
        .exclude(email="")
        .order_by("email")
        .values_list("email", flat=True)
    )


def _mensagens(resumo: ResumoCiclo, enderecos: list[str]):
    assunto = (
        f"FAROL: fechamento do ciclo {resumo.numero} ({resumo.inicio:%d/%m} a {resumo.fim:%d/%m})"
    )
    corpo = render_to_string(
        "relatorios/email_ciclo.txt",
        {"resumo": resumo, "site_url": settings.SITE_URL.rstrip("/")},
    )
    return [mail.EmailMessage(assunto, corpo, settings.DEFAULT_FROM_EMAIL, [e]) for e in enderecos]


def notificar_fechamento(hoje: date | None = None, reenviar: bool = False) -> dict:
    """Envia o e-mail do ciclo elegível. Devolve `{"status", "ciclo", "destinatarios"}`.

    `status`: `enviado`, `sem_ciclo` ou `sem_destinatarios`. Nunca devolve endereços."""
    hoje = hoje or timezone.localdate()
    if reenviar:
        ciclo = _fechados(hoje).order_by("-data_inicio").first()
    else:
        ciclo = ciclo_a_notificar(hoje)
    if ciclo is None:
        return {"status": "sem_ciclo", "ciclo": None, "destinatarios": 0}
    enderecos = destinatarios()
    if not enderecos:
        return {"status": "sem_destinatarios", "ciclo": ciclo, "destinatarios": 0}
    mensagens = _mensagens(resumo_do_ciclo(ciclo), enderecos)
    with transaction.atomic():
        registro, criado = NotificacaoCiclo.objects.get_or_create(
            ciclo=ciclo, defaults={"destinatarios": len(enderecos)}
        )
        if not criado:
            registro.destinatarios = len(enderecos)
            registro.save(update_fields=["destinatarios"])
        with mail.get_connection() as conexao:
            conexao.send_messages(mensagens)
    return {"status": "enviado", "ciclo": ciclo, "destinatarios": len(enderecos)}
