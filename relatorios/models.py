"""Modelos da camada: Relatórios e Notificações"""

from django.db import models

from core.historico import HistoricoPreservado
from core.models import CicloCalendario


class NotificacaoCiclo(HistoricoPreservado):
    """Registro de que o e-mail de fechamento de um ciclo já foi enviado (RF017).

    Garante o envio uma só vez por ciclo. Guarda só a contagem de destinatários: nunca
    endereços nem o corpo da mensagem. `criado_em` é a data do envio."""

    ciclo = models.OneToOneField(
        CicloCalendario, on_delete=models.PROTECT, related_name="notificacao"
    )
    destinatarios = models.PositiveIntegerField("destinatários")

    class Meta:
        verbose_name = "notificação de ciclo"
        verbose_name_plural = "notificações de ciclo"
