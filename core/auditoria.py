"""Auditoria de alterações (NF009): quem alterou, quando, e o valor anterior.

Reutilizada por qualquer tela que altere dado sensível (usuários, alunos, intervenções).
"""

from .models import RegistroAlteracao

CAMPOS_AUDITADOS_USUARIO = ("perfil", "is_active", "email", "first_name", "last_name")


def _texto(valor) -> str:
    return "" if valor is None else str(valor)


def registrar_alteracoes(*, autor, objeto, anteriores: dict) -> list[RegistroAlteracao]:
    """Grava uma linha por campo de `anteriores` cujo valor atual em `objeto` difere."""
    registros = []
    for campo, anterior in anteriores.items():
        antes, depois = _texto(anterior), _texto(getattr(objeto, campo))
        if antes != depois:
            registros.append(
                RegistroAlteracao(
                    autor=autor,
                    modelo=objeto._meta.label_lower,
                    objeto_id=str(objeto.pk),
                    campo=campo,
                    valor_anterior=antes,
                    valor_novo=depois,
                )
            )
    return RegistroAlteracao.objects.bulk_create(registros)


def historico_de(objeto):
    """Alterações do objeto, da mais recente para a mais antiga. Só para tela de Diretor."""
    return RegistroAlteracao.objects.filter(
        modelo=objeto._meta.label_lower, objeto_id=str(objeto.pk)
    ).select_related("autor")
