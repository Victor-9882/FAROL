"""Modelos de planilha para download, gerados em memória (nenhum binário no Git).

Reutilizável: cada importação (RF003 a RF006) passa suas colunas canônicas e linhas de
exemplo sintéticas. O cabeçalho é sempre o nome canônico das colunas.
"""

import csv
import io

from openpyxl import Workbook

TIPO_CSV = "text/csv; charset=utf-8"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _tabela(colunas, exemplos):
    colunas = list(colunas)
    return [colunas, *[[e.get(c, "") for c in colunas] for e in exemplos]]


def gerar_modelo_csv(colunas, exemplos) -> bytes:
    """CSV com `;` e BOM (abre direto no Excel em português)."""
    saida = io.StringIO()
    csv.writer(saida, delimiter=";", lineterminator="\n").writerows(_tabela(colunas, exemplos))
    return saida.getvalue().encode("utf-8-sig")


def gerar_modelo_xlsx(colunas, exemplos) -> bytes:
    livro = Workbook()
    aba = livro.active
    for linha in _tabela(colunas, exemplos):
        aba.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def gerar_modelo(nome: str, colunas, exemplos, formato: str) -> tuple[bytes, str, str]:
    """Devolve (conteúdo, tipo MIME, nome do arquivo) do modelo `nome` em `formato`."""
    if formato == "xlsx":
        return gerar_modelo_xlsx(colunas, exemplos), TIPO_XLSX, f"{nome}.xlsx"
    if formato == "csv":
        return gerar_modelo_csv(colunas, exemplos), TIPO_CSV, f"{nome}.csv"
    raise ValueError(f"Formato de modelo desconhecido: {formato}")
