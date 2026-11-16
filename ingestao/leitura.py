"""Leitura de planilhas (CSV e XLSX) em lista de dicionários (RF003 a RF006).

Reutilizada por todas as importações. Não grava nada no banco e não guarda o arquivo.
O XLSX é aberto em modo somente leitura e com `defusedxml` instalado (XXE e zip bomb).
Mensagens de erro nunca incluem conteúdo de células (LGPD).
"""

import csv
import io
import itertools
import os
import re
import unicodedata
import zipfile
from datetime import date, datetime

from django.conf import settings

TAMANHO_MAXIMO = 5 * 1024 * 1024  # bytes
EXTENSOES = (".csv", ".xlsx", ".xlsm")  # .xlsm: relatório do P+ (as macros nunca rodam)
LINHAS_PARA_CABECALHO = 10
MAX_COLUNAS = 50  # o XLSX em modo somente leitura preenche até a dimensão declarada da aba


class ArquivoInvalidoError(Exception):
    """Arquivo ilegível, de tipo não aceito ou sem as colunas esperadas."""


def normalizar_cabecalho(texto) -> str:
    """Minúsculas, sem acento; espaços e traços viram `_`."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[\s\-]+", "_", sem_acento.strip().lower())


def ler_data(valor) -> date | None:
    """Data de uma célula: `date`/`datetime` do XLSX ou texto `dd/mm/aaaa` ou `aaaa-mm-dd`."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(valor or "").strip(), formato).date()
        except ValueError:
            continue
    return None


def nome_arquivo_seguro(arquivo) -> str:
    """Nome do upload sem diretórios nem caracteres de controle, para a trilha."""
    nome = os.path.basename(arquivo.name.replace("\\", "/"))
    return "".join(c for c in nome if c.isprintable())[:255] or "arquivo"


def _celula(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str):
        return valor.strip()
    return valor


def _linhas_csv(conteudo: bytes, limite: int, max_colunas=MAX_COLUNAS) -> list[list]:
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252", errors="replace")
    primeira = texto.split("\n", 1)[0]
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.reader(io.StringIO(texto, newline=""), delimiter=separador)
    return [linha[:max_colunas] for linha in itertools.islice(leitor, limite + 2)]


def _linhas_xlsx(conteudo: bytes, limite: int, aba=None, max_colunas=MAX_COLUNAS) -> list[list]:
    from openpyxl import load_workbook

    try:
        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as erro:
        raise ArquivoInvalidoError("O arquivo XLSX não pôde ser lido.") from erro
    try:
        planilha = livro.worksheets[0]
        if aba:
            procurada = normalizar_cabecalho(aba)
            planilha = next(
                (p for p in livro.worksheets if normalizar_cabecalho(p.title) == procurada), None
            )
            if planilha is None:
                raise ArquivoInvalidoError(f"A aba “{aba}” não existe no arquivo.")
        linhas = planilha.iter_rows(values_only=True, max_col=max_colunas)
        return [list(linha) for linha in itertools.islice(linhas, limite + 2)]
    finally:
        livro.close()


def _achar_cabecalho(bruto: list[list], colunas, opcionais=frozenset()) -> int:
    """Índice do cabeçalho: a 1ª linha (entre as 10 primeiras) com todas as colunas exigidas."""
    if colunas:
        for indice, linha in enumerate(bruto[:LINHAS_PARA_CABECALHO]):
            nomes = {normalizar_cabecalho(c) for c in linha}
            if all(
                c in nomes or any(s in nomes for s in sin)
                for c, sin in colunas.items()
                if c not in opcionais
            ):
                return indice
    return 0


def ler_bruto(
    arquivo, nome_arquivo: str, *, aba=None, limite_linhas=None, max_colunas=MAX_COLUNAS
) -> list[list]:
    """Linhas cruas (listas de células) da aba `aba` do XLSX/XLSM (ou da primeira) ou do CSV,
    com as mesmas defesas de `ler_tabela`: extensão, tamanho e limite de linhas.

    Serve às planilhas que não são uma tabela simples, como a grade de presença (uma
    coluna por dia) e o relatório do P+ (duas abas)."""
    limite = limite_linhas if limite_linhas is not None else settings.IMPORTACAO_LIMITE_LINHAS
    nome = (nome_arquivo or "").lower()
    if not nome.endswith(EXTENSOES):
        raise ArquivoInvalidoError("Só são aceitos arquivos .csv, .xlsx e .xlsm.")
    conteudo = arquivo.read()
    if len(conteudo) > TAMANHO_MAXIMO:
        raise ArquivoInvalidoError("O arquivo excede o tamanho máximo permitido.")
    if nome.endswith(".csv"):
        bruto = [linha[:max_colunas] for linha in _linhas_csv(conteudo, limite, max_colunas)]
    else:
        bruto = _linhas_xlsx(conteudo, limite, aba, max_colunas)
    if len(bruto) < 2:
        raise ArquivoInvalidoError("O arquivo não tem linhas de dados.")
    if len(bruto) > limite + 1:
        raise ArquivoInvalidoError(f"O arquivo excede o limite de {limite} linhas.")
    return [[_celula(v) for v in linha] for linha in bruto]


def ler_tabela(
    arquivo,
    nome_arquivo: str,
    *,
    colunas: dict[str, tuple[str, ...]] | None = None,
    opcionais=frozenset(),
    limite_linhas: int | None = None,
    aba: str | None = None,
):
    """Lê a primeira aba (XLSX) ou o CSV e devolve uma lista de dicionários.

    `colunas` mapeia o nome canônico de cada coluna obrigatória aos sinônimos aceitos (já
    normalizados). Cada linha traz `_linha`, o número da linha no arquivo.
    O cabeçalho é a linha 1 ou, se `colunas` for dado, a primeira das 10 linhas iniciais que
    traga todas as colunas. As colunas em `opcionais` podem faltar no arquivo.
    Linhas totalmente vazias são puladas. Datas do XLSX viram `date`; matrícula numérica
    vira texto inteiro. `limite_linhas` troca o limite de linhas de dados, que por padrão é
    `settings.IMPORTACAO_LIMITE_LINHAS` (lido na chamada). `aba` escolhe a aba do XLSX pelo
    nome (sem distinção de caixa e acento).
    """
    bruto = ler_bruto(arquivo, nome_arquivo, aba=aba, limite_linhas=limite_linhas)

    inicio = _achar_cabecalho(bruto, colunas, opcionais)
    cabecalho = [normalizar_cabecalho(c) for c in bruto[inicio]]
    if colunas:
        renomear = {}
        for canonico, sinonimos in colunas.items():
            achado = next((c for c in cabecalho if c == canonico or c in sinonimos), None)
            if achado is None and canonico in opcionais:
                continue
            if achado is None:
                raise ArquivoInvalidoError(f"Coluna obrigatória ausente: {canonico}.")
            renomear[achado] = canonico
        cabecalho = [renomear.get(c, c) for c in cabecalho]

    linhas = []
    for numero, valores in enumerate(bruto[inicio + 1 :], start=inicio + 2):
        celulas = valores
        if all(v is None or v == "" for v in celulas):
            continue
        linha = {c: v for c, v in zip(cabecalho, celulas, strict=False) if c}
        matricula = linha.get("matricula")
        if isinstance(matricula, int | float) and not isinstance(matricula, bool):
            if float(matricula).is_integer():
                linha["matricula"] = str(int(matricula))
        linha["_linha"] = numero
        linhas.append(linha)
    if not linhas:
        raise ArquivoInvalidoError("O arquivo não tem linhas de dados.")
    return linhas
