"""Pendências de importação: linhas sem aluno correspondente (RN003, NF006, NF008, NF009).

As importações de frequência (RF003), simulados (RF004) e redação (RF005) associam cada
linha ao aluno só pela matrícula (RN003). Quando não dá (matrícula em branco, fora do
padrão, de outro ano letivo, não encontrada ou de aluno inválido), a linha vira uma
`PendenciaImportacao`, que o Diretor associa a um aluno ou descarta na tela de pendências.

- `LocalizadorAlunos` acha o aluno da linha ou diz o motivo da pendência.
- `registrar_pendencia` é idempotente: reimportar a mesma linha encontra a mesma pendência.
- `associar` aplica o que a linha traria por meio do aplicador da origem (registrado por
  cada importação com `@aplicador(origem)`) e audita a mudança de situação (NF009).
  O nome informado é só verificação: se difere do cadastro, a associação exige confirmação.

Mensagens e auditoria nunca trazem nome, matrícula ou notas.
"""

import hashlib
import json
from collections.abc import Callable

from django.db import transaction
from django.utils import timezone

from core.auditoria import registrar_alteracoes
from core.models import Aluno, PendenciaImportacao
from ingestao.base import linha_isolada
from ingestao.cadastro import _chave_nome, _espacos, validar_matricula

Motivo = PendenciaImportacao.Motivo
Origem = PendenciaImportacao.Origem
Situacao = PendenciaImportacao.Situacao

NOVA, PENDENTE, RESOLVIDA = "nova", "pendente", "resolvida"
NOME_DIVERGENTE = "o nome informado difere do cadastro; confirme a associação"
SEM_APLICADOR = "a importação desta origem ainda não sabe aplicar a pendência"

_MOTIVO_DA_VALIDACAO = {
    "matrícula fora do padrão": Motivo.FORA_DO_PADRAO,
    "matrícula de outro ano letivo": Motivo.OUTRO_ANO,
}

# origem -> função(pendencia, aluno, autor) -> motivo da recusa ("" se aplicou)
APLICADORES: dict[str, Callable] = {}


def aplicador(origem: str):
    """Registra a função que aplica uma pendência de `origem` ao aluno escolhido."""

    def registrar(funcao):
        APLICADORES[origem] = funcao
        return funcao

    return registrar


class AssociacaoRecusada(Exception):
    """A associação não pode ser feita; a mensagem não traz dado pessoal."""


class LocalizadorAlunos:
    """Acha o aluno de cada linha pela matrícula (RN003), com uma consulta só."""

    def __init__(self, matriculas, ano: int):
        self.ano = ano
        validas = {str(m).strip() for m in matriculas if m and str(m).strip()}
        self.alunos = Aluno.objects.in_bulk(list(validas))

    def localizar(self, matricula) -> tuple[Aluno | None, str]:
        """Devolve `(aluno, "")` ou `(None, motivo da pendência)`."""
        matricula = str(matricula or "").strip()
        if not matricula:
            return None, Motivo.EM_BRANCO
        motivo = validar_matricula(matricula, self.ano)
        if motivo:
            return None, _MOTIVO_DA_VALIDACAO[motivo]
        aluno = self.alunos.get(matricula)
        if aluno is None:
            return None, Motivo.NAO_ENCONTRADA
        if aluno.situacao == Aluno.Situacao.INVALIDO:
            return None, Motivo.ALUNO_INVALIDO
        return aluno, ""


def chave_pendencia(origem, ano, matricula, nome, referencia) -> str:
    """Identifica a linha entre reimportações (NF008): origem, ano, matrícula e nome
    informados e a referência da origem (dia, ciclo ou tema)."""
    partes = [str(origem), int(ano), str(matricula or "").strip(), _chave_nome(nome), referencia]
    texto = json.dumps(partes, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode()).hexdigest()


def pendencia_existente(*, origem, ano, matricula, nome, referencia):
    """A pendência já registrada para esta linha, se houver (com o aluno associado)."""
    chave = chave_pendencia(origem, ano, matricula, nome, referencia)
    return PendenciaImportacao.objects.filter(chave=chave).select_related("aluno").first()


def aluno_da_linha(localizador, *, origem, ano, matricula, nome, referencia):
    """Devolve `(aluno, motivo)`. Sem aluno pela matrícula, uma pendência já associada vale
    como o aluno escolhido pelo Diretor (a reimportação atualiza os dados dele); já
    descartada devolve `(None, RESOLVIDA)`; senão, `(None, motivo da pendência)`."""
    aluno, motivo = localizador.localizar(matricula)
    if aluno is not None:
        return aluno, ""
    pendencia = pendencia_existente(
        origem=origem, ano=ano, matricula=matricula, nome=nome, referencia=referencia
    )
    if pendencia is not None and pendencia.situacao == Situacao.ASSOCIADA:
        return pendencia.aluno, ""
    if pendencia is not None and pendencia.situacao == Situacao.DESCARTADA:
        return None, RESOLVIDA
    return None, motivo


def registrar_pendencia(
    *, origem, motivo, ano, data, matricula, nome, referencia, dados: dict
) -> str:
    """Cria a pendência ou reencontra a existente. Devolve `NOVA`, `PENDENTE` (já existia e
    continua pendente; `dados` atualizados) ou `RESOLVIDA` (já associada ou descartada:
    a linha deve ser ignorada pela importação)."""
    chave = chave_pendencia(origem, ano, matricula, nome, referencia)
    existente = PendenciaImportacao.objects.filter(chave=chave).first()
    if existente is None:
        PendenciaImportacao.objects.create(
            origem=origem,
            motivo=motivo,
            ano=ano,
            data=data,
            matricula_informada=str(matricula or "").strip()[:30],
            nome_informado=_espacos(nome)[:150],
            dados=dados,
            chave=chave,
        )
        return NOVA
    if existente.situacao != Situacao.PENDENTE:
        return RESOLVIDA
    if existente.dados != dados or existente.motivo != motivo:
        existente.dados, existente.motivo = dados, motivo
        existente.save(update_fields=["dados", "motivo"])
    return PENDENTE


def nome_divergente(pendencias, aluno) -> bool:
    """Alguma pendência traz um nome diferente do cadastro (caixa, acento e espaço à parte)?"""
    cadastro = _chave_nome(aluno.nome)
    return any(p.nome_informado and _chave_nome(p.nome_informado) != cadastro for p in pendencias)


def _resolver(pendencia, situacao, autor, quando, aluno=None):
    anteriores = {"situacao": pendencia.situacao}
    pendencia.situacao = situacao
    pendencia.aluno = aluno
    pendencia.resolvida_por = autor
    pendencia.resolvida_em = quando
    pendencia.save(update_fields=["situacao", "aluno", "resolvida_por", "resolvida_em"])
    # Só a situação vai para a auditoria: nunca nome, matrícula ou notas.
    registrar_alteracoes(autor=autor, objeto=pendencia, anteriores=anteriores)


@transaction.atomic
def associar(pendencias, aluno, *, autor, confirmar_nome=False) -> tuple[int, list]:
    """Associa em grupo as pendências ainda pendentes ao `aluno`.

    Recusa tudo (`AssociacaoRecusada`) se o aluno é inválido, de outro ano letivo, ou se o
    nome diverge sem `confirmar_nome`. Cada pendência é aplicada num savepoint: a que o
    aplicador recusar continua pendente e volta em `recusas` como `(id, motivo)`.
    Devolve `(associadas, recusas)`."""
    pendentes = [p for p in pendencias if p.situacao == Situacao.PENDENTE]
    if aluno.situacao == Aluno.Situacao.INVALIDO:
        raise AssociacaoRecusada("o aluno escolhido está marcado como inválido")
    if any(validar_matricula(aluno.matricula, p.ano) for p in pendentes):
        raise AssociacaoRecusada("o aluno escolhido não é do ano letivo da pendência")
    if not confirmar_nome and nome_divergente(pendentes, aluno):
        raise AssociacaoRecusada(NOME_DIVERGENTE)
    agora = timezone.now()
    associadas, recusas = 0, []
    for pendencia in pendentes:
        aplicar = APLICADORES.get(pendencia.origem)
        if aplicar is None:
            recusas.append((pendencia.pk, SEM_APLICADOR))
            continue
        motivos = []
        with linha_isolada(motivos.append):  # restrição do banco ou validação do modelo
            try:
                with transaction.atomic():
                    motivo = aplicar(pendencia, aluno, autor)
                    if motivo:
                        raise _Desfazer(motivo)
            except _Desfazer as recusa:
                motivos.append(str(recusa))
        if motivos:
            recusas.append((pendencia.pk, motivos[0]))
            continue
        _resolver(pendencia, Situacao.ASSOCIADA, autor, agora, aluno)
        associadas += 1
    return associadas, recusas


@transaction.atomic
def descartar(pendencias, *, autor) -> int:
    """Descarta as pendências ainda pendentes (ficam preservadas, NF007). Devolve quantas."""
    agora = timezone.now()
    pendentes = [p for p in pendencias if p.situacao == Situacao.PENDENTE]
    for pendencia in pendentes:
        _resolver(pendencia, Situacao.DESCARTADA, autor, agora)
    return len(pendentes)


class _Desfazer(Exception):
    """Desfaz o savepoint quando o aplicador recusa a pendência depois de gravar algo."""
