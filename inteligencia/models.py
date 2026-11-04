"""Modelos da camada de Inteligência."""

from django.db import models

from core.historico import HistoricoPreservado


class RegraAlerta(HistoricoPreservado):
    """Regra interpretável que origina alertas (NF021), com limiar ajustável (RF018).

    Os limiares ficam no banco, e não no código, para a Direção ajustá-los sem
    nova versão do sistema. Ao mudar um limiar, desative a regra antiga e crie
    outra: assim os alertas antigos continuam apontando para o limiar que os gerou.
    """

    class Tipo(models.TextChoices):
        FREQUENCIA = "FREQUENCIA", "Frequência semanal"  # RF014
        DESEMPENHO = "DESEMPENHO", "Queda de desempenho no ciclo"  # RF015
        EVOLUCAO = "EVOLUCAO", "Evolução consistente"  # RF016

    tipo_regra = models.CharField("tipo de regra", max_length=12, choices=Tipo.choices)
    limiar = models.DecimalField(max_digits=7, decimal_places=2)
    descricao = models.TextField(
        "descrição", help_text="Como a regra é aplicada, em linguagem simples."
    )
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "regra de alerta"
        verbose_name_plural = "regras de alerta"
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_regra"],
                condition=models.Q(ativa=True),
                name="uma_regra_ativa_por_tipo",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_regra_display()} (limiar {self.limiar})"
