"""Regera os alertas de frequência (RF014) e de desempenho (RF015) de um ano letivo.

Idempotente (NF005): pode rodar a cada noite, por um agendador, ou depois de correções.
"""

from datetime import date

from django.core.management.base import BaseCommand

from inteligencia.alertas import gerar_ano


class Command(BaseCommand):
    help = "Regera os alertas de frequência e de desempenho do ano letivo."

    def add_arguments(self, parser):
        parser.add_argument("--ano", type=int, default=date.today().year)

    def handle(self, *args, ano, **options):
        frequencia, desempenho = gerar_ano(ano)
        for nome, g in (("frequência", frequencia), ("desempenho", desempenho)):
            if g.sem_regra:
                self.stdout.write(self.style.WARNING(f"{nome}: sem regra ativa, nada gerado"))
                continue
            self.stdout.write(
                f"{nome}: {g.novos} novo(s), {g.atualizados} atualizado(s), "
                f"{g.desativados} desativado(s), {g.mantidos} sem mudança"
            )
