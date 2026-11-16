"""Base comum das importações (NF006, NF008, NF011, NF025).

Cada importação (cadastro, calendário, catraca...) escreve só a validação da linha e a
aplicação no banco; daqui vêm o resumo com os totais, a triagem (linha inválida ou repetida
não interrompe), a transação que desfaz quando só se confere e o isolamento por linha.
Nada aqui guarda arquivo nem conteúdo de célula: as mensagens são fixas (LGPD).
"""

from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

MOTIVO_RESTRICAO = "registro recusado por uma restrição do banco"
MOTIVO_VALIDACAO = "registro recusado pela validação do modelo"


@dataclass
class ResumoImportacao:
    """Totais de uma importação. `total_linhas` sempre fecha com as linhas do arquivo:
    importados + ignorados + divergentes + inconsistentes."""

    criados: int = 0
    atualizados: int = 0
    sem_alteracao: int = 0
    inconsistentes: list[tuple] = field(default_factory=list)
    avisos: list[tuple[int, str]] = field(default_factory=list)
    # Registros do banco que a importação sobrepõe (NF008); preenchida pelas importações
    # de dados que se repetem (RF003 em diante). A conferência é a confirmação.
    sobreposicoes: list[str] = field(default_factory=list)

    @property
    def importados(self) -> int:
        return self.criados + self.atualizados

    @property
    def ignorados(self) -> int:
        """Linha válida que não mudou nada."""
        return self.sem_alteracao

    @property
    def divergentes(self) -> int:
        """Linha válida cujo conteúdo difere do banco e não foi aplicada (ver o cadastro)."""
        return 0

    @property
    def total_linhas(self) -> int:
        return self.importados + self.ignorados + self.divergentes + len(self.inconsistentes)

    def assinatura(self) -> list[int]:
        """Números que a conferência mostrou; o token de confirmação os carrega.

        Cada contador vai separado: se um registro "a criar" passou a existir entre a conferência
        e a confirmação (e seria sobrescrito), a assinatura muda e a confirmação é recusada."""
        return [
            self.criados,
            self.atualizados,
            self.sem_alteracao,
            self.divergentes,
            len(self.inconsistentes),
            len(self.sobreposicoes),
        ]


def triar(
    linhas: Iterable[dict],
    validar: Callable[[dict], tuple[dict | None, str]],
    *,
    chave: Callable[[dict], object],
    recusar: Callable[[dict, str], None],
    repetida: str = "registro repetido no arquivo",
) -> list[tuple[int, dict]]:
    """Valida cada linha e devolve `(número, dados)` das válidas e únicas pela `chave`.
    Inválidas e repetidas vão para `recusar(linha, motivo)` sem interromper as demais."""
    validas, vistas = [], set()
    for linha in linhas:
        dados, motivo = validar(linha)
        if dados is None:
            recusar(linha, motivo)
            continue
        valor = chave(dados)
        if valor in vistas:
            recusar(linha, repetida)
            continue
        vistas.add(valor)
        validas.append((linha["_linha"], dados))
    return validas


@contextmanager
def transacao_de_importacao(gravar: bool):
    """Transação da importação; com `gravar=False` tudo é desfeito ao sair (conferência)."""
    with transaction.atomic():
        yield
        if not gravar:
            transaction.set_rollback(True)


@contextmanager
def linha_isolada(recusar: Callable[[str], None]):
    """Savepoint por linha: uma restrição do banco ou uma validação do modelo recusa só
    aquela linha. O motivo nunca traz o valor da célula."""
    try:
        with transaction.atomic():
            yield
    except IntegrityError:
        recusar(MOTIVO_RESTRICAO)
    except ValidationError as erro:
        partes = []
        if hasattr(erro, "error_dict"):
            campos = [c for c in erro.error_dict if c != "__all__"]
            if campos:
                partes.append("campos inválidos: " + ", ".join(campos))
            partes += _mensagens(erro.error_dict.get("__all__", []))
        else:
            partes = _mensagens(erro.error_list)
        recusar("; ".join(partes))


def _mensagens(erros) -> list[str]:
    """Mensagem com `params` pode interpolar o valor da célula: vira o motivo genérico."""
    return [MOTIVO_VALIDACAO if e.params else str(e.message) for e in erros]
