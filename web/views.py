"""Views da camada de Apresentação."""

from django.db import connection
from django.http import JsonResponse


def saude(request):
    """Verificação de saúde: confirma que a aplicação está no ar e alcança o banco."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
