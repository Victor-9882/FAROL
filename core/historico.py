"""Preservação do histórico (NF007).

Nenhum registro de aluno, turma, frequência, desempenho, alerta ou intervenção
é excluído fisicamente: o histórico precisa sobreviver às trocas anuais de
gestão do CASD. Os modelos que herdam de `HistoricoPreservado` recusam
`delete()`, tanto no objeto quanto em querysets.
"""

from django.db import models


class ExclusaoProibidaError(Exception):
    """Tentativa de excluir fisicamente um registro de histórico (NF007)."""


def _recusar_exclusao(modelo) -> None:
    raise ExclusaoProibidaError(
        f"{modelo._meta.verbose_name_plural} fazem parte do histórico e não podem ser "
        "excluídos (NF007)."
    )


class HistoricoQuerySet(models.QuerySet):
    def delete(self):
        _recusar_exclusao(self.model)


class HistoricoPreservado(models.Model):
    """Base dos modelos cujo histórico é preservado entre anos letivos e gestões."""

    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    objects = HistoricoQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        _recusar_exclusao(self)
