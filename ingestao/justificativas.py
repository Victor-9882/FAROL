"""Justificativa de falta (RF008, RN002, RN004, RN005, NF009).

Registrar a justificativa pela tela é aprová-la (RN002: "aprovada pela Direção"); quem registra
é o Diretor. Só se justifica falta que já existe como `RegistroFrequencia(presente=False)`: a
tela não cria registros. O motivo não é guardado (sem texto livre); a trilha é o
`RegistroAlteracao` (autor, data e valor anterior). Retirar a justificativa também é permitido.
"""

from django.db import transaction

from core.auditoria import registrar_alteracoes
from core.calendario import dias_letivos, eh_dia_letivo
from core.models import RegistroFrequencia
from inteligencia.indicadores import no_curso


class JustificativaRecusada(Exception):
    """A falta não pode receber (nem perder) justificativa. Mensagem genérica, sem dados."""


def faltas_do_aluno(aluno) -> list[RegistroFrequencia]:
    """Faltas do aluno em dia letivo (RN005) e dentro da sua janela (RN004), da mais recente
    à mais antiga."""
    faltas = list(RegistroFrequencia.objects.filter(aluno=aluno, presente=False))
    if not faltas:
        return []
    datas = [f.data for f in faltas]
    letivos = set(dias_letivos(min(datas), max(datas)))
    validas = [
        f
        for f in faltas
        if f.data in letivos and no_curso(f.data, aluno.data_ingresso, aluno.data_saida)
    ]
    return sorted(validas, key=lambda f: f.data, reverse=True)


def _alterar(registro, valor: bool, *, autor) -> bool:
    with transaction.atomic():
        atual = (
            RegistroFrequencia.objects.select_for_update()
            .select_related("aluno")
            .get(pk=registro.pk)
        )
        aluno = atual.aluno
        if atual.presente:
            raise JustificativaRecusada("só falta pode ser justificada")
        if not eh_dia_letivo(atual.data):
            raise JustificativaRecusada("o dia não é letivo")
        if not no_curso(atual.data, aluno.data_ingresso, aluno.data_saida):
            raise JustificativaRecusada("o dia está fora do período do aluno no curso")
        if atual.justificada == valor:
            registro.justificada = atual.justificada
            return False
        antes = atual.justificada
        atual.justificada = valor
        atual.save(update_fields=["justificada"])
        registrar_alteracoes(autor=autor, objeto=atual, anteriores={"justificada": antes})
        registro.justificada = valor
        return True


def justificar(registro, *, autor) -> bool:
    """Justifica a falta; devolve False (sem auditar) se já estava justificada."""
    return _alterar(registro, True, autor=autor)


def retirar_justificativa(registro, *, autor) -> bool:
    """Retira a justificativa; devolve False (sem auditar) se não havia."""
    return _alterar(registro, False, autor=autor)
