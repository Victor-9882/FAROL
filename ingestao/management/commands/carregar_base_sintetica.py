"""Carrega a base sintética no banco de desenvolvimento, para ver o painel com dados."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ingestao.demonstracao import carregar


class Command(BaseCommand):
    help = "Carrega um ano da base sintética (tests/dados_sinteticos). Só com DEBUG ligado."

    def add_arguments(self, parser):
        parser.add_argument("--ano", type=int, default=2026)
        parser.add_argument("--autor", required=True, help="username do Diretor que assina")

    def handle(self, *args, ano, autor, **options):
        if not settings.DEBUG:
            raise CommandError("Só em desenvolvimento (DEBUG ligado): a base é sintética.")
        usuario = get_user_model().objects.filter(username=autor, perfil="DIRETOR").first()
        if usuario is None:
            raise CommandError("Informe o username de um Diretor existente em --autor.")
        contagens = carregar(ano, autor=usuario)
        self.stdout.write(self.style.SUCCESS(f"Base sintética de {ano} carregada: {contagens}"))
