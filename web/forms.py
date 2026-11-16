"""Formulários de gestão de usuários (RF002, NF009).

`fields` é sempre explícito: `is_staff`, `is_superuser`, grupos e permissões nunca
entram em formulário (escalada de privilégio). Superusuários são geridos só no admin.
"""

from django import forms
from django.db import transaction

from core.auditoria import CAMPOS_AUDITADOS_USUARIO, registrar_alteracoes
from core.models import Usuario

CAMPOS_AUDITADOS = CAMPOS_AUDITADOS_USUARIO


class _EmailUnico(forms.ModelForm):
    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        outros = Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if outros.exists():
            raise forms.ValidationError("Já existe um usuário com este e-mail.")
        return email


class UsuarioNovoForm(_EmailUnico):
    """Cria o usuário sem senha: o acesso é liberado por link de uso único."""

    class Meta:
        model = Usuario
        fields = ["username", "first_name", "last_name", "email", "perfil"]

    def __init__(self, *args, autor, **kwargs):
        super().__init__(*args, **kwargs)
        self.autor = autor

    def save(self, commit=True):
        with transaction.atomic():
            usuario = super().save(commit=False)
            usuario.set_unusable_password()
            usuario.save()
            registrar_alteracoes(autor=self.autor, objeto=usuario, anteriores={"perfil": ""})
        return usuario


class UsuarioEdicaoForm(_EmailUnico):
    """Edita dados e perfil; `username` é imutável e revogar é desativar (sem exclusão)."""

    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "email", "perfil", "is_active"]
        labels = {"is_active": "Acesso ativo"}

    def __init__(self, *args, autor, **kwargs):
        super().__init__(*args, **kwargs)
        self.autor = autor
        # is_valid() altera self.instance; guardar o estado original antes.
        self._anteriores = {c: getattr(self.instance, c) for c in CAMPOS_AUDITADOS}

    def clean(self):
        dados = super().clean()
        era_diretor_ativo = (
            self._anteriores["perfil"] == Usuario.Perfil.DIRETOR and self._anteriores["is_active"]
        )
        continua = dados.get("perfil") == Usuario.Perfil.DIRETOR and dados.get("is_active")
        if era_diretor_ativo and "perfil" in dados and not continua:
            outro = (
                Usuario.objects.filter(perfil=Usuario.Perfil.DIRETOR, is_active=True)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if not outro:
                raise forms.ValidationError(
                    "Deve restar ao menos um Diretor ativo. Promova outro usuário antes."
                )
        return dados

    def save(self, commit=True):
        with transaction.atomic():
            usuario = super().save()
            registrar_alteracoes(autor=self.autor, objeto=usuario, anteriores=self._anteriores)
        return usuario
