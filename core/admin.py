from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.contrib.auth.admin import UserAdmin
from django.db import transaction

from .auditoria import CAMPOS_AUDITADOS_USUARIO, registrar_alteracoes
from .models import RegistroAlteracao, Usuario

# Auditoria no admin (NF009): além dos campos da tela, o que só o admin altera.
CAMPOS_AUDITADOS_ADMIN = (*CAMPOS_AUDITADOS_USUARIO, "username", "is_staff", "is_superuser")


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "email", "perfil", "is_active")
    list_filter = ("perfil", "is_active")
    fieldsets = (*UserAdmin.fieldsets, ("FAROL", {"fields": ("perfil",)}))
    add_fieldsets = (*UserAdmin.add_fieldsets, ("FAROL", {"fields": ("email", "perfil")}))

    # RN013/NF013: só superusuário gerencia contas e perfil; staff comum tem no máximo leitura.
    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)

    # NF009: toda alteração de conta feita pelo admin gera RegistroAlteracao (RF002).
    # `save_model` já roda dentro do atomic do admin, junto com a gravação.
    def save_model(self, request, obj, form, change):
        if change:
            antigo = Usuario.objects.get(pk=obj.pk)
            anteriores = {c: getattr(antigo, c) for c in CAMPOS_AUDITADOS_ADMIN}
        else:
            anteriores = {"perfil": ""}
        super().save_model(request, obj, form, change)
        registrar_alteracoes(autor=request.user, objeto=obj, anteriores=anteriores)

    def user_change_password(self, request, id, form_url=""):
        # Não passa por save_model. Compara o hash só em memória; nunca o grava.
        with transaction.atomic():
            antes = (
                Usuario.objects.filter(pk=unquote(id)).values_list("password", flat=True).first()
            )
            resposta = super().user_change_password(request, id, form_url)
            alvo = Usuario.objects.filter(pk=unquote(id)).first()
            if alvo is not None and antes is not None and alvo.password != antes:
                RegistroAlteracao.objects.create(
                    autor=request.user,
                    modelo=alvo._meta.label_lower,
                    objeto_id=str(alvo.pk),
                    campo="senha",
                    valor_anterior="",
                    valor_novo=(
                        "senha alterada pelo admin"
                        if alvo.has_usable_password()
                        else "senha desativada pelo admin"
                    ),
                )
            return resposta
