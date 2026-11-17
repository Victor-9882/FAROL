"""Carrega a base sintética no banco de desenvolvimento, para ver o painel com dados."""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ingestao.demonstracao import BASE, carregar


class Command(BaseCommand):
    help = "Carrega um ano da base sintética. Só com DEBUG ligado."

    def add_arguments(self, parser):
        parser.add_argument("--ano", type=int, default=2026)
        parser.add_argument("--autor", required=True, help="username do Diretor que assina")
        parser.add_argument(
            "--base",
            type=Path,
            help="Pasta com os anos sintéticos (padrão: tests/dados_sinteticos/pequena).",
        )

    def handle(self, *args, ano, autor, base, **options):
        if not settings.DEBUG:
            raise CommandError("Só em desenvolvimento (DEBUG ligado): a base é sintética.")
        usuario = get_user_model().objects.filter(username=autor, perfil="DIRETOR").first()
        if usuario is None:
            raise CommandError("Informe o username de um Diretor existente em --autor.")
        contagens = carregar(ano, autor=usuario, base=base or BASE)
        self.stdout.write(self.style.SUCCESS(f"Base sintética de {ano} carregada: {contagens}"))
