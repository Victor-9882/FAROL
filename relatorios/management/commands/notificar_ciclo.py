"""Envia o e-mail de fechamento do ciclo (RF017). Agende depois de `gerar_alertas`."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from relatorios.notificacoes import notificar_fechamento


class Command(BaseCommand):
    help = "Envia o e-mail agregado do ciclo recém-encerrado, uma vez por ciclo."

    def add_arguments(self, parser):
        parser.add_argument("--data", help="Data de referência (AAAA-MM-DD); padrão: hoje.")
        parser.add_argument("--reenviar", action="store_true", help="Envia de novo o último ciclo.")

    def handle(self, *args, **opcoes):
        try:
            hoje = date.fromisoformat(opcoes["data"]) if opcoes["data"] else None
        except ValueError as erro:
            raise CommandError("Use --data no formato AAAA-MM-DD.") from erro
        r = notificar_fechamento(hoje, reenviar=opcoes["reenviar"])
        if r["status"] == "sem_ciclo":
            self.stdout.write("Nenhum ciclo fechado com resultados a notificar. Nada enviado.")
        elif r["status"] == "sem_destinatarios":
            self.stdout.write("Nenhum destinatário com e-mail. Nada enviado nem registrado.")
        else:
            self.stdout.write(f"Ciclo notificado: {r['destinatarios']} destinatário(s).")
