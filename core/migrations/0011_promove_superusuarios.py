from django.db import migrations


def promover(apps, schema_editor):
    """Promove a Diretor os superusuários com perfil Membro (RN013, NF013, NF009).

    A restrição `superusuario_e_diretor` (migração 0012) exige essa regra. O autor do
    registro de auditoria é a própria conta promovida, porque uma migração não tem outro autor.
    """
    Usuario = apps.get_model("core", "Usuario")
    RegistroAlteracao = apps.get_model("core", "RegistroAlteracao")
    for usuario in Usuario.objects.filter(is_superuser=True).exclude(perfil="DIRETOR"):
        anterior = usuario.perfil
        usuario.perfil = "DIRETOR"
        usuario.save(update_fields=["perfil"])
        RegistroAlteracao.objects.create(
            autor=usuario,
            modelo="core.usuario",
            objeto_id=str(usuario.pk),
            campo="perfil",
            valor_anterior=anterior,
            valor_novo="DIRETOR",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_alerta_semana_e_ativo"),
    ]

    operations = [
        migrations.RunPython(promover, migrations.RunPython.noop),
    ]
