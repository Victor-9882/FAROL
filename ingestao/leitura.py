"""Leitura de planilhas (CSV e XLSX) em lista de dicionários (RF003 a RF006).

Reutilizada por todas as importações. Não grava nada no banco e não guarda o arquivo.
O XLSX é aberto em modo somente leitura e com `defusedxml` instalado (XXE e zip bomb).
Mensagens de erro nunca incluem conteúdo de células (LGPD).
"""

import csv
import io
import re
import unicodedata
import zipfile
from datetime import datetime

TAMANHO_MAXIMO = 5 * 1024 * 1024  # bytes
LIMITE_LINHAS = 5000
EXTENSOES = (".csv", ".xlsx")
LINHAS_PARA_CABECALHO = 10


class ArquivoInvalidoError(Exception):
    """Arquivo ilegível, de tipo não aceito ou sem as colunas esperadas."""


def normalizar_cabecalho(texto) -> str:
    """Minúsculas, sem acento; espaços e traços viram `_`."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[\s\-]+", "_", sem_acento.strip().lower())


def _celula(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str):
        return valor.strip()
    return valor


def _linhas_csv(conteudo: bytes) -> list[list]:
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252", errors="replace")
    primeira = texto.split("\n", 1)[0]
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    return list(csv.reader(io.StringIO(texto, newline=""), delimiter=separador))


def _linhas_xlsx(conteudo: bytes) -> list[list]:
    from openpyxl import load_workbook

    try:
        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as erro:
        raise ArquivoInvalidoError("O arquivo XLSX não pôde ser lido.") from erro
    try:
        return [list(linha) for linha in livro.worksheets[0].iter_rows(values_only=True)]
    finally:
        livro.close()


def _achar_cabecalho(bruto: list[list], colunas) -> int:
    """Índice do cabeçalho: a 1ª linha (entre as 10 primeiras) com todas as colunas exigidas."""
    if colunas:
        for indice, linha in enumerate(bruto[:LINHAS_PARA_CABECALHO]):
            nomes = {normalizar_cabecalho(c) for c in linha}
            if all(c in nomes or any(s in nomes for s in sin) for c, sin in colunas.items()):
                return indice
    return 0


def ler_tabela(arquivo, nome_arquivo: str, *, colunas: dict[str, tuple[str, ...]] | None = None):
    """Lê a primeira aba (XLSX) ou o CSV e devolve uma lista de dicionários.

    `colunas` mapeia o nome canônico de cada coluna obrigatória aos sinônimos aceitos (já
    normalizados). Cada linha traz `_linha`, o número da linha no arquivo.
    O cabeçalho é a linha 1 ou, se `colunas` for dado, a primeira das 10 linhas iniciais que
    traga todas as colunas.
    Linhas totalmente vazias são puladas. Datas do XLSX viram `date`; matrícula numérica
    vira texto inteiro.
    """
    nome = (nome_arquivo or "").lower()
    if not nome.endswith(EXTENSOES):
        raise ArquivoInvalidoError("Só são aceitos arquivos .csv e .xlsx.")
    conteudo = arquivo.read()
    if len(conteudo) > TAMANHO_MAXIMO:
        raise ArquivoInvalidoError("O arquivo excede o tamanho máximo permitido.")
    bruto = _linhas_xlsx(conteudo) if nome.endswith(".xlsx") else _linhas_csv(conteudo)
    if len(bruto) < 2:
        raise ArquivoInvalidoError("O arquivo não tem linhas de dados.")
    if len(bruto) > LIMITE_LINHAS + 1:
        raise ArquivoInvalidoError(f"O arquivo excede o limite de {LIMITE_LINHAS} linhas.")

    inicio = _achar_cabecalho(bruto, colunas)
    cabecalho = [normalizar_cabecalho(c) for c in bruto[inicio]]
    if colunas:
        renomear = {}
        for canonico, sinonimos in colunas.items():
            achado = next((c for c in cabecalho if c == canonico or c in sinonimos), None)
            if achado is None:
                raise ArquivoInvalidoError(f"Coluna obrigatória ausente: {canonico}.")
            renomear[achado] = canonico
        cabecalho = [renomear.get(c, c) for c in cabecalho]

    linhas = []
    for numero, valores in enumerate(bruto[inicio + 1 :], start=inicio + 2):
        celulas = [_celula(v) for v in valores]
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
