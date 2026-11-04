"""Modelos da Aplicação Core."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """Membro da gestão do CASD que acessa o FAROL (RF001, RF002).

    O perfil define o que é exibido: só o Diretor vê dados nominais (RN013, NF013).
    O padrão é Membro, o perfil mais restrito.
    """

    class Perfil(models.TextChoices):
        DIRETOR = "DIRETOR", "Diretor"
        MEMBRO = "MEMBRO", "Membro de diretoria"

    email = models.EmailField("e-mail", unique=True)
    perfil = models.CharField(max_length=10, choices=Perfil.choices, default=Perfil.MEMBRO)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    @property
    def is_diretor(self) -> bool:
        return self.perfil == self.Perfil.DIRETOR
