"""Carga dos valores padrão das regras de alerta (IC-10): `config/regras_padrao.yaml`."""

from django.db import migrations


def carregar(apps, schema_editor):
    from inteligencia.regras import criar_padroes

    criar_padroes(apps.get_model("inteligencia", "RegraAlerta"))


class Migration(migrations.Migration):
    dependencies = [("inteligencia", "0001_initial")]

    operations = [migrations.RunPython(carregar, migrations.RunPython.noop)]
