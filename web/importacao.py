"""Fluxo único das telas de importação: conferir sempre, gravar só com token (NF006, NF008).

Nada é guardado no servidor: nem o arquivo, nem sessão, nem cache. A conferência devolve um
token assinado (`ingestao.confirmacao`) preso ao usuário, ao arquivo, aos parâmetros e aos
números do resumo. Confirmar reprocessa o arquivo dentro de uma transação e só grava se o
token confere; se algo mudou (arquivo, parâmetros, dados no banco) ou se o token expirou, a
transação é desfeita e a tela volta a ser uma conferência, com novo token.
"""

import io
from dataclasses import dataclass

from django.db import transaction

from core.models import RegistroImportacao
from ingestao.base import ResumoImportacao
from ingestao.confirmacao import emitir_token, impressao_digital, token_confere
from ingestao.leitura import ArquivoInvalidoError, ler_tabela, nome_arquivo_seguro

AVISO_MUDOU = (
    "O arquivo, os parâmetros ou os dados mudaram desde a conferência, ou ela expirou. "
    "Confira o novo resumo e confirme de novo."
)


@dataclass
class ResultadoImportacao:
    resumo: ResumoImportacao | None = None
    gravado: bool = False
    token: str = ""
    aviso: str = ""


def executar_importacao(
    request,
    form,
    *,
    colunas,
    opcionais=frozenset(),
    parametros: dict,
    importar,
    registrar,
    limite_linhas=None,
    ler=None,
) -> ResultadoImportacao:
    """`importar(linhas, gravar) -> ResumoImportacao`; `registrar(nome, tamanho, resumo)` grava
    a trilha. `parametros` são os valores do formulário (em texto) que o token deve proteger.
    `ler(arquivo, nome)` substitui `ler_tabela` nas planilhas que não são uma tabela simples
    (grade de presença, relatório do P+); deve levantar `ArquivoInvalidoError`."""
    resultado = ResultadoImportacao()
    if request.method != "POST" or not form.is_valid():
        return resultado
    arquivo = form.cleaned_data["arquivo"]
    conteudo = arquivo.read()
    digital = impressao_digital(conteudo)
    try:
        if ler is not None:
            linhas = ler(io.BytesIO(conteudo), arquivo.name)
        else:
            linhas = ler_tabela(
                io.BytesIO(conteudo),
                arquivo.name,
                colunas=colunas,
                opcionais=opcionais,
                limite_linhas=limite_linhas,
            )
    except ArquivoInvalidoError as erro:
        form.add_error("arquivo", str(erro))
        return resultado

    def confere(token, resumo):
        return token_confere(
            token,
            usuario_id=request.user.pk,
            arquivo=digital,
            parametros=parametros,
            resumo=resumo.assinatura(),
        )

    token = request.POST.get("token", "")
    if request.POST.get("acao") == "importar" and token:
        with transaction.atomic():
            resumo = importar(linhas, True)
            if confere(token, resumo):
                registrar(nome_arquivo_seguro(arquivo), arquivo.size, resumo)
                resultado.resumo, resultado.gravado = resumo, True
                return resultado
            transaction.set_rollback(True)
        resultado.aviso = AVISO_MUDOU
    else:
        resumo = importar(linhas, False)
    resultado.resumo = resumo
    resultado.token = emitir_token(
        usuario_id=request.user.pk,
        arquivo=digital,
        parametros=parametros,
        resumo=resumo.assinatura(),
    )
    return resultado


def registrar_trilha(*, autor, tipo, ano, nome, tamanho, resumo, **extras):
    """Trilha do upload (NF007, NF009): só nome do arquivo, tamanho e contagens do resumo."""
    return RegistroImportacao.objects.create(
        autor=autor,
        tipo=tipo,
        nome_arquivo=nome,
        tamanho_bytes=tamanho,
        ano=ano,
        criados=resumo.criados,
        atualizados=resumo.atualizados,
        sem_alteracao=resumo.sem_alteracao,
        inconsistentes=len(resumo.inconsistentes),
        pendencias=len(resumo.pendencias),
        **extras,
    )
