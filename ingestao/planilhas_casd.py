"""Layouts das planilhas que o CASD usa no dia a dia (RF003, RF004, RF005).

Os cabeçalhos abaixo reproduzem os das planilhas reais (as amostras ficam só na pasta
restrita do Drive, NF017), com uma diferença combinada com a equipe em 16/11/2026: a grade
de presença e o relatório do P+ ganham a coluna `Matrícula`, porque a associação ao aluno é
pela matrícula (RN003). No Corrija-me, a matrícula vai na coluna `RM`, que já existe.

Este módulo também *gera* planilhas nesses layouts, sempre com dados passados por quem chama:
os modelos para download (linhas de exemplo sintéticas), o gerador da base sintética e os
testes. Nunca recebe nem grava dado real.
"""

import io
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta

from openpyxl import Workbook

# --- Frequência: grade "Presença Anual" (Controle de Presença AAAA.xlsx) ------------------

ABA_PRESENCA = "Presença Anual"
CODIGOS_PRESENCA = {
    "P": "presente",
    "F": "falta",
    "J": "falta justificada (RN002)",
    "S": "sem aula",
}

# --- Simulados: relatório do P+ (uma avaliação por arquivo) -------------------------------

ABA_NOTAS_PMAIS = "Resultados e Classificações TRI"
ABA_ACERTOS_PMAIS = "Acertos e Porcentagens TRI"
# área do FAROL -> (nome da área no P+, etapa). Etapa 1: 1º dia; Etapa 2: 2º dia.
AREAS_PMAIS = {
    "HUMANAS": ("Ciências Humanas", 1),
    "LINGUAGENS": ("Linguagens e Códigos", 1),
    "NATUREZA": ("Ciências da Natureza", 2),
    "MATEMATICA": ("Matemática", 2),
}
_ORDEM_NOTAS = ("HUMANAS", "LINGUAGENS", "NATUREZA", "MATEMATICA")
_ORDEM_ACERTOS = ("NATUREZA", "HUMANAS", "LINGUAGENS", "MATEMATICA")
_IDENTIFICACAO_PMAIS = [
    "Nome Avaliação",
    "ID Escola",
    "Escola",
    "ID Turma ",
    "Ano/Série",
    "Turma",
    "Ano letivo",
    "ID Aluno",
    "Inscrição",
    "E-mail p4ed",
    "Nome Aluno",
    "Matrícula",  # acrescentada pela equipe (RN003)
]

# --- Redação: exportação do Corrija-me -----------------------------------------------------

ABA_CORRIJA_ME = "Worksheet"
COLUNAS_CORRIJA_ME = [
    "ID DA REDACAO",
    "ID DA ATIVIDADE",
    "DATA ENVIO",
    "DATA CORREÇÃO",
    "NOME COMPLETO",
    "EMAIL",
    "RM",
    "BANCA",
    "TEMA",
    "C1",
    "C2",
    "C3",
    "C4",
    "C5",
    "NOTAL FINAL",  # sic: é assim que o Corrija-me exporta
    "EMPRESA",
    "POLO",
    "LOCAL",
    "ESCOLA",
    "UNIDADE",
    "ENSINO",
    "SERIE",
    "PERIODO",
    "TURMA",
]


def chave(texto) -> str:
    """Normaliza um cabeçalho real: minúsculas, sem acento, pontuação vira espaço."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


_DATA_FIXA = datetime(2026, 1, 1)


def _salvar(livro) -> bytes:
    """Salva com datas fixas (metadados e zip): a mesma planilha gera sempre os mesmos bytes,
    o que mantém a base sintética reprodutível."""
    livro.properties.created = livro.properties.modified = _DATA_FIXA
    bruto = io.BytesIO()
    livro.save(bruto)
    saida = io.BytesIO()
    with (
        zipfile.ZipFile(bruto) as origem,
        zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zip_,
    ):
        for item in origem.infolist():
            fixo = zipfile.ZipInfo(item.filename, date_time=_DATA_FIXA.timetuple()[:6])
            fixo.compress_type = zipfile.ZIP_DEFLATED
            dados = origem.read(item.filename)
            if item.filename == "docProps/core.xml":  # o openpyxl grava a hora do save
                dados = re.sub(
                    rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*",
                    rb"\g<1>" + _DATA_FIXA.strftime("%Y-%m-%dT%H:%M:%SZ").encode(),
                    dados,
                )
            zip_.writestr(fixo, dados)
    return saida.getvalue()


def grade_presenca(ano: int, alunos: list[dict], codigos: dict) -> bytes:
    """Grade "Presença Anual": `alunos` com `nome`, `matricula` e `turma`; `codigos` mapeia
    `(matricula, data)` a P, F, J ou S. As colunas de dia são os dias úteis entre a primeira
    e a última data de `codigos`, agrupados por semana, como na planilha do CASD."""
    livro = Workbook()
    aba = livro.active
    aba.title = ABA_PRESENCA
    datas = sorted({d for _, d in codigos})
    dias = []
    if datas:
        dia = datas[0] - timedelta(days=datas[0].weekday())
        while dia <= datas[-1]:
            if dia.weekday() < 5:
                dias.append(dia)
            dia += timedelta(days=1)
    semanas: list[list[date]] = []
    for dia in dias:
        if not semanas or dia.weekday() == 0:
            semanas.append([])
        semanas[-1].append(dia)

    titulo = [None, None, f"Controle de Presença {ano}"]
    linha_semanas = [None] * 7
    cabecalho = ["Nome", "Matrícula", "Turma", "% Presença", None, "Faltas totais", None]
    for numero, semana in enumerate(semanas, 1):
        linha_semanas += [f"Semana {numero}"] + [None] * len(semana)
        cabecalho += [*semana, "Faltas", None]
    aba.append(titulo)
    aba.append(linha_semanas)
    aba.append(cabecalho)
    for aluno in alunos:
        linha = [aluno["nome"], aluno["matricula"], aluno["turma"]]
        celulas, faltas_total, presencas, contadas = [], 0, 0, 0
        for semana in semanas:
            faltas = 0
            for dia in semana:
                codigo = codigos.get((aluno["matricula"], dia), "")
                celulas.append(codigo)
                faltas += codigo == "F"
                presencas += codigo == "P"
                contadas += codigo in ("P", "F")
            celulas += [faltas, None]
            faltas_total += faltas
        percentual = round(presencas / contadas, 4) if contadas else 0
        aba.append([*linha, percentual, None, faltas_total, None, *celulas])
    return _salvar(livro)


def relatorio_pmais(avaliacao: str, ano: int, alunos: list[dict]) -> bytes:
    """Relatório do P+ com as duas abas usadas: `alunos` com `matricula`, `nome`, `id_aluno`,
    `inscricao`, `turma` e, por área do FAROL, `notas[area]` (TRI) e `acertos[area]`, ambos
    `None` quando o aluno faltou à etapa."""
    livro = Workbook()
    notas = livro.active
    notas.title = ABA_NOTAS_PMAIS
    acertos = livro.create_sheet(ABA_ACERTOS_PMAIS)
    cab_notas = list(_IDENTIFICACAO_PMAIS) + [
        "Nota Geral",
        "Posição no sistema de ensino",
        "Posição na escola",
    ]
    for area in _ORDEM_NOTAS:
        nome, etapa = AREAS_PMAIS[area]
        cab_notas += [
            f"{nome} - Etapa {etapa} - Nota ",
            f"{nome} - Etapa {etapa} - Posição no Sistema de Ensino ",
            f"{nome} - Etapa {etapa}-  Posição na Escola ",
        ]
    cab_acertos = list(_IDENTIFICACAO_PMAIS) + [
        "Questões Totais",
        "Acertos Totais",
        "Porcentagem Total",
    ]
    for area in _ORDEM_ACERTOS:
        nome, _ = AREAS_PMAIS[area]
        cab_acertos += [f"{nome} - Questões", f"{nome} - Acertos", f"{nome} - Porcentagem"]
    notas.append(cab_notas)
    acertos.append(cab_acertos)
    for posicao, aluno in enumerate(alunos, 1):
        ident = [
            avaliacao,
            9000,
            "Escola Sintética",
            9100,
            "PV ",
            f"CASDvest {ano} - {aluno['turma']}",
            ano,
            aluno["id_aluno"],
            aluno["inscricao"],
            f"aluno{aluno['id_aluno']}@exemplo.org",
            aluno["nome"],
            aluno["matricula"],
        ]
        tri = [aluno["notas"].get(a) for a in _ORDEM_NOTAS]
        validas = [n for n in tri if isinstance(n, int | float)]
        linha = ident + [round(sum(validas) / 4, 2) if validas else None, None, posicao]
        for nota in tri:
            linha += [nota, None, None]
        notas.append(linha)
        feitos = [aluno["acertos"].get(a) for a in _ORDEM_ACERTOS]
        total = sum(n for n in feitos if n is not None)
        linha = ident + [180, total, f"{total / 180:.2%}".replace(".", ",")]
        for feito in feitos:
            if feito is None:
                linha += [None, None, None]
            else:
                linha += [45, feito, f"{feito / 45:.2%}".replace(".", ",")]
        acertos.append(linha)
    return _salvar(livro)


def exportacao_corrija_me(redacoes: list[dict]) -> bytes:
    """Exportação do Corrija-me: uma linha por redação entregue. Cada item traz `id`,
    `atividade`, `envio` e `correcao` (datetime), `nome`, `rm`, `banca`, `tema`, `notas`
    (lista C1 a C5, `None` onde a banca não tem o critério), `final` e `turma`."""
    livro = Workbook()
    aba = livro.active
    aba.title = ABA_CORRIJA_ME
    aba.append(COLUNAS_CORRIJA_ME)
    for r in redacoes:
        aba.append(
            [
                r["id"],
                r["atividade"],
                f"{r['envio']:%d/%m/%Y %H:%M:%S}",
                f"{r['correcao']:%d/%m/%Y %H:%M:%S}",
                r["nome"],
                f"redacao{r['id']}@exemplo.org",
                r["rm"],
                r["banca"],
                r["tema"],
                *r["notas"],
                r["final"],
                "CASD",
                "Padrão",
                "Padrão",
                "Padrão",
                "Padrão",
                "Pré-Vestibular",
                "Padrão",
                "Noite",
                r["turma"],
            ]
        )
    return _salvar(livro)
