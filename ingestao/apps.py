from django.apps import AppConfig


class IngestaoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ingestao"
    verbose_name = "Ingestão"

    def ready(self):
        # Registra os aplicadores de pendências de cada importação (`ingestao.pendencias`).
        from . import frequencia, redacoes, simulados  # noqa: F401
