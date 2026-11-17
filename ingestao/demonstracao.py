"""Carga da base sintética num banco de desenvolvimento ou de teste (NF017).

Serve para ver o painel e as consultas com dados (v0.3.0) e para os testes de integração dos
indicadores. Só lê `tests/dados_sinteticos/` (dados inventados) e só roda com `DEBUG` ligado
ou em teste (`manage.py carregar_base_sintetica`); nunca em produção.

O cadastro, o calendário e a frequência passam pelas importações de verdade (com as
réplicas das planilhas reais quando existem); simulados e redações de todos os ciclos e
temas são gravados direto dos CSVs, que têm o ano inteiro (as réplicas trazem só alguns).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.test.utils import override_settings

from core.models import (
    Aluno,
    CicloCalendario,
    PeriodoLetivo,
    ResultadoRedacao,
    ResultadoSimulado,
    TemaRedacao,
)
from ingestao.cadastro import COLUNAS as COLUNAS_CADASTRO
from ingestao.cadastro import importar_cadastro
from ingestao.calendario import TIPOS
from ingestao.frequencia import importar_frequencia, ler_grade
from ingestao.leitura import ler_tabela
from inteligencia.alertas import gerar_ano

BASE = Path(settings.BASE_DIR) / "tests" / "dados_sinteticos" / "pequena"
SIGLAS = {"LC": "LINGUAGENS", "CH": "HUMANAS", "CN": "NATUREZA", "MT": "MATEMATICA"}


def _d(texto: str) -> date:
    dia, mes, ano = map(int, texto.split("/"))
    return date(ano, mes, dia)


def _csv(pasta: Path, nome: str, colunas=None, opcionais=frozenset()):
    with (pasta / nome).open("rb") as arquivo:
        return ler_tabela(arquivo, nome, colunas=colunas, opcionais=opcionais)


@transaction.atomic
@override_settings(IMPORTACAO_LIMITE_LINHAS=200_000)
def carregar(ano: int, *, autor, base: Path = BASE) -> dict:
    """Carrega um ano sintético, inclusive a base de carga, sem alterar limites de uploads.

    O limite elevado vale apenas nesta função de desenvolvimento. As importações normais
    continuam sujeitas a `IMPORTACAO_LIMITE_LINHAS`.
    """
    pasta = base / str(ano)
    importar_cadastro(
        _csv(pasta, "cadastro_alunos.csv", COLUNAS_CADASTRO, frozenset({"data_ingresso"})),
        ano=ano,
        autor=autor,
        data_mudanca=date(ano, 6, 25),
        gravar=True,
    )
    calendario = _csv(pasta, "calendario_letivo.csv", {"data": ()})
    PeriodoLetivo.objects.get_or_create(
        inicio=_d(calendario[0]["data"]),
        defaults={"fim": _d(calendario[-1]["data"]), "descricao": "Ano letivo (base sintética)"},
    )
    for slug in ("dias", "ciclos", "temas"):
        tipo = TIPOS[slug]
        nome = {
            "dias": "calendario_letivo.csv",
            "ciclos": "ciclos.csv",
            "temas": "temas_redacao.csv",
        }
        tipo.importar(
            _csv(pasta, nome[slug], tipo.colunas, tipo.opcionais), ano=ano, autor=autor, gravar=True
        )

    grade = pasta / "planilhas" / "presenca_anual.xlsx"
    if grade.exists():
        with grade.open("rb") as arquivo:
            importar_frequencia(
                ler_grade(arquivo, grade.name, ano=ano), ano=ano, autor=autor, gravar=True
            )

    alunos = set(Aluno.objects.filter(turma__ano=ano).values_list("pk", flat=True))
    ciclos = {c.data_simulado: c for c in CicloCalendario.objects.filter(data_inicio__year=ano)}
    novos = []
    for linha in _csv(pasta, "p_mais_simulados.csv", {"matricula": ()}):
        ciclo = ciclos.get(_d(linha["data"]))
        if ciclo is None or linha["matricula"] not in alunos:
            continue
        presente = linha["presenca"] == "Presente"
        for sigla, area in SIGLAS.items():
            novos.append(
                ResultadoSimulado(
                    aluno_id=linha["matricula"],
                    ciclo=ciclo,
                    area=area,
                    presente=presente,
                    acertos=int(linha[f"{sigla.lower()}_acertos"]) if presente else None,
                    nota_tri=Decimal(str(linha[f"{sigla.lower()}_tri"]).replace(",", "."))
                    if presente
                    else None,
                )
            )
    ResultadoSimulado.objects.bulk_create(novos, ignore_conflicts=True)

    temas = dict(TemaRedacao.objects.filter(data__year=ano).values_list("data", "tema"))
    redacoes = []
    for linha in _csv(pasta, "corrija_me_redacoes.csv", {"matricula": ()}):
        terca = _d(linha["data_tema"])
        if linha["matricula"] not in alunos or terca not in temas:
            continue
        entregue = linha["entregue"] == "S"
        notas = {f"nota_c{n}": Decimal(linha[f"c{n}"]) if entregue else None for n in range(1, 6)}
        redacoes.append(
            ResultadoRedacao(
                aluno_id=linha["matricula"],
                tema_semana=terca,
                tema=temas[terca],
                entregue=entregue,
                banca="ENEM" if entregue else "",
                **notas,
            )
        )
    ResultadoRedacao.objects.bulk_create(redacoes, ignore_conflicts=True)
    frequencia, desempenho = gerar_ano(ano)
    return {
        "alunos": len(alunos),
        "simulados": len(novos),
        "redacoes": len(redacoes),
        "alertas": frequencia.novos + desempenho.novos,
    }
