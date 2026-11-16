from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


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
