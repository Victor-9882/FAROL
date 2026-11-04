#!/usr/bin/env python3
"""Gera a base sintética do FAROL (NF017, NF012; Plano de Testes, Seção 5).

Produz, para cada ano letivo, arquivos no formato das fontes do CASD: cadastro,
calendário, catraca, P+ e Corrija-me. Também inclui perfis de aluno com
resultado conhecido, usados nos testes das regras de alerta.

Nenhum dado real é usado, nem como inspiração: os nomes são combinações
aleatórias de listas genéricas e as matrículas começam com "S", formato que
o CASD não usa.

    uv run python scripts/gerar_base_sintetica.py                     # pequena, versionada
    uv run python scripts/gerar_base_sintetica.py --tamanho completa  # 500 alunos/ano

O formato dos arquivos está descrito em tests/dados_sinteticos/README.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO_PADRAO = RAIZ / "tests" / "dados_sinteticos"
SEMENTE_PADRAO = 28


@dataclass(frozen=True)
class Tamanho:
    alunos_por_turma: int
    turmas: int = 5
    anos: tuple[int, ...] = (2024, 2025, 2026)


TAMANHOS = {
    "pequena": Tamanho(alunos_por_turma=4),
    "completa": Tamanho(alunos_por_turma=100),  # 500 alunos por ano (NF012)
}

PRIMEIROS_NOMES = [
    "Ana", "Bruno", "Carla", "Daniel", "Eduarda", "Felipe", "Gabriela", "Henrique",
    "Isabela", "João", "Karen", "Lucas", "Mariana", "Nicolas", "Olívia", "Paulo",
    "Rafaela", "Samuel", "Tatiane", "Vinícius", "Yasmin", "Arthur", "Beatriz", "Caio",
    "Débora", "Enzo", "Fernanda", "Gustavo", "Helena", "Igor", "Júlia", "Leonardo",
    "Manuela", "Otávio", "Pietra", "Renan", "Sofia", "Thiago", "Valentina", "Wesley",
]  # fmt: skip
SOBRENOMES = [
    "Almeida", "Barbosa", "Cardoso", "Dias", "Esteves", "Ferreira", "Gomes", "Henriques",
    "Lima", "Martins", "Nogueira", "Oliveira", "Pereira", "Queiroz", "Ribeiro", "Santos",
    "Teixeira", "Vieira", "Andrade", "Batista", "Campos", "Duarte", "Freitas", "Garcia",
    "Lopes", "Machado", "Moreira", "Nunes", "Pinto", "Ramos", "Rocha", "Souza",
]  # fmt: skip
TEMAS = [
    "Desafios da mobilidade urbana", "O acesso à cultura nas periferias",
    "Saúde mental na juventude", "A desinformação nas redes sociais",
    "Trabalho e tecnologia", "O papel da ciência na sociedade",
    "Desperdício de alimentos", "Inclusão digital de idosos",
    "Preservação dos recursos hídricos", "Educação financeira nas escolas",
]  # fmt: skip

# Áreas do simulado (RN010): sigla usada nas colunas do P+ -> nome.
AREAS = {"LC": "Linguagens", "CH": "Humanas", "CN": "Natureza", "MT": "Matemática"}
QUESTOES_POR_AREA = 45
NOTAS_COMPETENCIA = (0, 40, 80, 120, 160, 200)


# --- Calendário ----------------------------------------------------------------------


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return date(ano, mes, dia)


def feriados(ano: int) -> dict[date, str]:
    """Feriados nacionais e de São José dos Campos (aproximação para a base sintética)."""
    p = pascoa(ano)
    fixos = {
        (1, 1): "Confraternização Universal",
        (3, 19): "Dia de São José (municipal)",
        (4, 21): "Tiradentes",
        (5, 1): "Dia do Trabalho",
        (7, 27): "Aniversário de São José dos Campos",
        (9, 7): "Independência do Brasil",
        (10, 12): "Nossa Senhora Aparecida",
        (11, 2): "Finados",
        (11, 15): "Proclamação da República",
        (11, 20): "Dia da Consciência Negra",
        (12, 25): "Natal",
    }
    datas = {date(ano, m, d): nome for (m, d), nome in fixos.items()}
    datas[p - timedelta(days=48)] = "Carnaval"
    datas[p - timedelta(days=47)] = "Carnaval"
    datas[p - timedelta(days=2)] = "Sexta-feira Santa"
    datas[p + timedelta(days=60)] = "Corpus Christi"
    return datas


def proxima_segunda(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


@dataclass
class Ciclo:
    numero: int
    inicio: date  # segunda-feira
    fim: date  # domingo, dia do simulado

    @property
    def simulado(self) -> date:
        return self.fim


@dataclass
class Calendario:
    ano: int
    inicio: date
    fim: date
    recesso: tuple[date, date]
    feriados: dict[date, str]
    dias_letivos: list[date] = field(default_factory=list)
    ciclos: list[Ciclo] = field(default_factory=list)
    temas: list[tuple[date, str]] = field(default_factory=list)

    def em_recesso(self, d: date) -> bool:
        return self.recesso[0] <= d <= self.recesso[1]


def montar_calendario(ano: int) -> Calendario:
    """Ano letivo de fevereiro a novembro, segunda a sexta, com recesso de julho (RN005)."""
    inicio = proxima_segunda(date(ano, 2, 2))
    fim = date(ano, 11, 27)
    while fim.weekday() != 4:  # última sexta-feira até 27/11
        fim -= timedelta(days=1)
    inicio_recesso = proxima_segunda(date(ano, 7, 1))
    cal = Calendario(
        ano=ano,
        inicio=inicio,
        fim=fim,
        recesso=(inicio_recesso, inicio_recesso + timedelta(days=13)),
        feriados=feriados(ano),
    )

    d = inicio
    while d <= fim:
        if d.weekday() < 5 and d not in cal.feriados and not cal.em_recesso(d):
            cal.dias_letivos.append(d)
        d += timedelta(days=1)

    # Ciclos de duas semanas, com simulado no domingo que fecha o ciclo (RN006).
    segunda = inicio
    while segunda + timedelta(days=13) <= fim + timedelta(days=2):
        if cal.em_recesso(segunda) or cal.em_recesso(segunda + timedelta(days=13)):
            segunda = cal.recesso[1] + timedelta(days=1)
            continue
        cal.ciclos.append(Ciclo(len(cal.ciclos) + 1, segunda, segunda + timedelta(days=13)))
        segunda += timedelta(days=14)

    # Tema novo de redação toda terça-feira, fora do recesso (RN007).
    terca = inicio + timedelta(days=1)
    while terca <= fim:
        if not cal.em_recesso(terca):
            cal.temas.append((terca, f"{TEMAS[len(cal.temas) % len(TEMAS)]}"))
        terca += timedelta(days=7)
    return cal


# --- Alunos --------------------------------------------------------------------------


@dataclass
class Aluno:
    matricula: str
    nome: str
    ingresso: date
    turmas: list[tuple[str, date]]  # (turma, início); a última é a atual
    assiduidade: float = 0.9
    nota_base: dict[str, float] = field(default_factory=dict)
    tendencia: float = 0.0
    prob_simulado: float = 0.9
    prob_redacao: float = 0.75
    nivel_redacao: int = 3  # índice em NOTAS_COMPETENCIA
    perfil: str | None = None
    # Perfis com resultado conhecido sobrescrevem o comportamento aleatório:
    faltas_fixas: dict[date, bool] = field(default_factory=dict)  # data -> justificada?
    simulados_ausente: set[int] = field(default_factory=set)
    notas_fixas: dict[int, float] | None = None  # ciclo -> nota TRI em todas as áreas

    def turma_em(self, d: date) -> str:
        atual = self.turmas[0][0]
        for turma, inicio in self.turmas:
            if inicio <= d:
                atual = turma
        return atual


def nome_aleatorio(rng: random.Random) -> str:
    sobrenomes = rng.sample(SOBRENOMES, 2)
    return f"{rng.choice(PRIMEIROS_NOMES)} {sobrenomes[0]} {sobrenomes[1]}"


def semana_completa(cal: Calendario, depois_de: date) -> list[date]:
    """Primeira semana, a partir de `depois_de`, com os cinco dias letivos."""
    segunda = proxima_segunda(depois_de)
    letivos = set(cal.dias_letivos)
    while True:
        semana = [segunda + timedelta(days=i) for i in range(5)]
        if all(d in letivos for d in semana):
            return semana
        segunda += timedelta(days=7)


def criar_alunos(cal: Calendario, tamanho: Tamanho, rng: random.Random, perfis: bool):
    turmas = [f"Turma {chr(ord('A') + i)}" for i in range(tamanho.turmas)]
    chamadas = [cal.inicio, cal.inicio + timedelta(weeks=5), cal.inicio + timedelta(weeks=10)]
    alunos: list[Aluno] = []
    for turma in turmas:
        for _ in range(tamanho.alunos_por_turma):
            ingresso = rng.choices(chamadas, weights=[75, 15, 10])[0]
            base = rng.gauss(560, 70)
            alunos.append(
                Aluno(
                    matricula=f"S{cal.ano % 100:02d}{len(alunos) + 1:04d}",
                    nome=nome_aleatorio(rng),
                    ingresso=ingresso,
                    turmas=[(turma, ingresso)],
                    assiduidade=rng.uniform(0.75, 0.98),
                    nota_base={a: base + rng.gauss(0, 30) for a in AREAS},
                    tendencia=rng.gauss(0, 3),
                    prob_simulado=rng.uniform(0.8, 0.98),
                    prob_redacao=rng.uniform(0.4, 0.95),
                    nivel_redacao=rng.randint(2, 4),
                )
            )

    # Uma mudança de turma aleatória por ano, além do perfil conhecido (RN011).
    meio_do_ano = proxima_segunda(date(cal.ano, 8, 3))
    candidato = rng.choice(alunos[len(turmas) * 2 :] if perfis else alunos)
    nova = rng.choice([t for t in turmas if t != candidato.turmas[0][0]])
    candidato.turmas.append((nova, meio_do_ano))

    if perfis:
        aplicar_perfis(cal, alunos, turmas)
    return alunos


def aplicar_perfis(cal: Calendario, alunos: list[Aluno], turmas: list[str]) -> None:
    """Transforma os primeiros alunos em perfis com resultado conhecido."""
    semana = semana_completa(cal, date(cal.ano, 4, 1))
    mudanca = cal.dias_letivos[len(cal.dias_letivos) // 2]
    segunda_chamada = cal.inicio + timedelta(weeks=5)

    def preparar(aluno: Aluno, perfil: str, turma: str | None = None) -> Aluno:
        aluno.perfil = perfil
        aluno.ingresso = cal.inicio
        aluno.turmas = [(turma or aluno.turmas[0][0], cal.inicio)]
        aluno.assiduidade = 1.0
        aluno.prob_simulado = 1.0
        aluno.prob_redacao = 1.0
        aluno.nivel_redacao = 3
        aluno.notas_fixas = {c.numero: 600.0 for c in cal.ciclos}
        return aluno

    tres_faltas = preparar(alunos[0], "tres_faltas_na_semana")
    tres_faltas.faltas_fixas = {d: False for d in semana[:3]}

    justificada = preparar(alunos[1], "falta_justificada")
    justificada.faltas_fixas = {semana[0]: False, semana[1]: False, semana[2]: True}

    ausente = preparar(alunos[2], "ausente_no_simulado")
    ausente.simulados_ausente = {cal.ciclos[5].numero}

    mudou = preparar(alunos[3], "mudou_de_turma", turma=turmas[0])
    mudou.turmas.append((turmas[1], mudanca))

    tardio = preparar(alunos[4], "segunda_chamada")
    tardio.ingresso = segunda_chamada
    tardio.turmas = [(tardio.turmas[0][0], segunda_chamada)]

    queda = preparar(alunos[5], "queda_de_desempenho")
    queda.notas_fixas = {c.numero: (650.0 if c.numero < 8 else 590.0) for c in cal.ciclos}

    evolucao = preparar(alunos[6], "evolucao_consistente")
    evolucao.notas_fixas = {c.numero: 500.0 + 15 * (c.numero - 1) for c in cal.ciclos}


def descrever_perfis(cal: Calendario, alunos: list[Aluno]) -> list[dict]:
    """Resultado esperado de cada perfil, para os testes das regras."""
    por_perfil = {a.perfil: a for a in alunos if a.perfil}
    semana = sorted(por_perfil["tres_faltas_na_semana"].faltas_fixas)
    mudou = por_perfil["mudou_de_turma"]
    queda_ciclo = 8
    return [
        {
            "perfil": "tres_faltas_na_semana",
            "matricula": por_perfil["tres_faltas_na_semana"].matricula,
            "descricao": "Presente em todos os dias letivos, exceto em três dias seguidos "
            "da mesma semana, sem justificativa.",
            "esperado": {
                "semana": fmt(semana[0]),
                "faltas_nao_justificadas": 3,
                "datas": [fmt(d) for d in semana],
            },
        },
        {
            "perfil": "falta_justificada",
            "matricula": por_perfil["falta_justificada"].matricula,
            "descricao": "Três ausências na mesma semana, uma delas justificada e aprovada "
            "(RN002): só duas contam como falta.",
            "esperado": {
                "semana": fmt(semana[0]),
                "ausencias": 3,
                "faltas_nao_justificadas": 2,
                "data_justificada": fmt(semana[2]),
            },
        },
        {
            "perfil": "ausente_no_simulado",
            "matricula": por_perfil["ausente_no_simulado"].matricula,
            "descricao": "Faltou a um simulado: não é avaliado em desempenho naquele ciclo "
            "(RN009). Nota 600 em todas as áreas nos demais.",
            "esperado": {"ciclo_ausente": 6, "data_simulado": fmt(cal.ciclos[5].simulado)},
        },
        {
            "perfil": "mudou_de_turma",
            "matricula": mudou.matricula,
            "descricao": "Mudou de turma no meio do ano; o histórico anterior deve ser "
            "preservado (RN011).",
            "esperado": {
                "turma_anterior": mudou.turmas[0][0],
                "turma_nova": mudou.turmas[1][0],
                "data_mudanca": fmt(mudou.turmas[1][1]),
            },
        },
        {
            "perfil": "segunda_chamada",
            "matricula": por_perfil["segunda_chamada"].matricula,
            "descricao": "Ingressou na segunda chamada: não tem registros nem faltas antes "
            "do ingresso (RN004).",
            "esperado": {"data_ingresso": fmt(por_perfil["segunda_chamada"].ingresso)},
        },
        {
            "perfil": "queda_de_desempenho",
            "matricula": por_perfil["queda_de_desempenho"].matricula,
            "descricao": "Nota TRI 650 em todas as áreas até o ciclo 7 e 590 a partir do "
            "ciclo 8: queda de 60 pontos em relação ao próprio histórico (RN008).",
            "esperado": {"ciclo_queda": queda_ciclo, "delta_tri": -60.0},
        },
        {
            "perfil": "evolucao_consistente",
            "matricula": por_perfil["evolucao_consistente"].matricula,
            "descricao": "Nota TRI sobe 15 pontos em todas as áreas a cada ciclo (RF016).",
            "esperado": {"delta_tri_por_ciclo": 15.0, "nota_ciclo_1": 500.0},
        },
    ]


# --- Arquivos ------------------------------------------------------------------------


def fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def decimal_br(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",")


def escrever(caminho: Path, cabecalho: list[str], linhas) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        saida = csv.writer(arquivo, delimiter=";", lineterminator="\n")
        saida.writerow(cabecalho)
        saida.writerows(linhas)


def gerar_ano(destino: Path, cal: Calendario, alunos: list[Aluno], rng: random.Random):
    pasta = destino / str(cal.ano)

    escrever(
        pasta / "cadastro_alunos.csv",
        ["matricula", "nome", "turma", "data_ingresso"],
        [(a.matricula, a.nome, a.turmas[-1][0], fmt(a.ingresso)) for a in alunos],
    )
    historico = []
    for a in alunos:
        for i, (turma, inicio) in enumerate(a.turmas):
            fim = a.turmas[i + 1][1] if i + 1 < len(a.turmas) else None
            historico.append((a.matricula, turma, fmt(inicio), fmt(fim) if fim else ""))
    escrever(
        pasta / "historico_turmas.csv",
        ["matricula", "turma", "data_inicio", "data_fim"],
        historico,
    )

    calendario = []
    d = cal.inicio
    while d <= cal.fim:
        if d.weekday() < 5:
            if d in cal.feriados:
                calendario.append((fmt(d), "N", cal.feriados[d]))
            elif cal.em_recesso(d):
                calendario.append((fmt(d), "N", "Recesso escolar"))
            else:
                calendario.append((fmt(d), "S", ""))
        d += timedelta(days=1)
    escrever(pasta / "calendario_letivo.csv", ["data", "dia_letivo", "descricao"], calendario)
    escrever(
        pasta / "ciclos.csv",
        ["ciclo", "data_inicio", "data_fim", "data_simulado"],
        [(c.numero, fmt(c.inicio), fmt(c.fim), fmt(c.simulado)) for c in cal.ciclos],
    )
    escrever(
        pasta / "temas_redacao.csv",
        ["data", "tema"],
        [(fmt(d), tema) for d, tema in cal.temas],
    )

    # Catraca: uma linha por passagem; a falta é a ausência de linha (RN001).
    catraca, justificativas = [], []
    for d in cal.dias_letivos:
        for a in alunos:
            if d < a.ingresso:
                continue
            if a.perfil:
                presente = d not in a.faltas_fixas
                justificada = a.faltas_fixas.get(d, False)
            else:
                presente = rng.random() < a.assiduidade
                justificada = not presente and rng.random() < 0.15
            if presente:
                catraca.append((fmt(d), a.matricula, a.nome))
            elif justificada:
                justificativas.append((fmt(d), a.matricula, "S"))

    # P+: uma linha por aluno e simulado, com acertos e nota TRI por área (RN010).
    simulados = []
    for c in cal.ciclos:
        for a in alunos:
            if c.simulado < a.ingresso:
                continue
            nome_simulado = f"Simulado {c.numero} - {cal.ano}"
            if a.perfil:
                presente = c.numero not in a.simulados_ausente
            else:
                presente = rng.random() < a.prob_simulado
            if not presente:
                simulados.append(
                    (nome_simulado, fmt(c.simulado), a.matricula, a.nome, "Ausente")
                    + ("",) * (2 * len(AREAS))
                )
                continue
            colunas = []
            for area in AREAS:
                if a.notas_fixas is not None:
                    tri = a.notas_fixas[c.numero]
                else:
                    tri = a.nota_base[area] + a.tendencia * c.numero + rng.gauss(0, 25)
                    tri = min(max(tri, 300.0), 900.0)
                acertos = round(QUESTOES_POR_AREA * (tri - 300) / 600)
                colunas += [str(min(max(acertos, 0), QUESTOES_POR_AREA)), decimal_br(tri)]
            simulados.append(
                (nome_simulado, fmt(c.simulado), a.matricula, a.nome, "Presente", *colunas)
            )

    # Corrija-me: uma linha por aluno e tema semanal (RN007).
    redacoes = []
    for d, tema in cal.temas:
        for a in alunos:
            if d < a.ingresso:
                continue
            if a.perfil or rng.random() < a.prob_redacao:
                if a.perfil:
                    notas = [NOTAS_COMPETENCIA[a.nivel_redacao]] * 5
                else:
                    notas = [
                        NOTAS_COMPETENCIA[min(max(a.nivel_redacao + rng.randint(-1, 1), 0), 5)]
                        for _ in range(5)
                    ]
                redacoes.append((fmt(d), tema, a.matricula, a.nome, "S", *notas, sum(notas)))
            else:
                redacoes.append((fmt(d), tema, a.matricula, a.nome, "N", *[""] * 6))

    return pasta, catraca, justificativas, simulados, redacoes


def gerar(destino: Path, tamanho: Tamanho, semente: int = SEMENTE_PADRAO) -> dict:
    """Gera a base em `destino` e devolve o resumo (também gravado em perfis_conhecidos.json)."""
    rng = random.Random(semente)
    resumo = {"semente": semente, "anos": {}, "perfis": [], "inconsistencias": []}
    cabecalho_p_mais = ["simulado", "data", "matricula", "nome", "presenca"]
    for area in AREAS:
        cabecalho_p_mais += [f"{area}_acertos", f"{area}_tri"]

    for ano in tamanho.anos:
        cal = montar_calendario(ano)
        ultimo_ano = ano == tamanho.anos[-1]
        alunos = criar_alunos(cal, tamanho, rng, perfis=ultimo_ano)
        pasta, catraca, justificativas, simulados, redacoes = gerar_ano(destino, cal, alunos, rng)

        if ultimo_ano:
            resumo["perfis"] = descrever_perfis(cal, alunos)
            # Inconsistências conhecidas, para os testes de importação tolerante (NF006).
            dia = fmt(cal.dias_letivos[10])
            catraca.append((dia, "S999999", "Passagem Sem Cadastro"))
            orfa = alunos[-1]
            tema_data, tema_nome = cal.temas[3]
            redacoes.append((fmt(tema_data), tema_nome, "", orfa.nome, "S", *[120] * 5, 600))
            resumo["inconsistencias"] = [
                {
                    "tipo": "matricula_desconhecida",
                    "arquivo": f"{ano}/catraca_presencas.csv",
                    "matricula": "S999999",
                    "data": dia,
                },
                {
                    "tipo": "matricula_em_branco",
                    "arquivo": f"{ano}/corrija_me_redacoes.csv",
                    "nome": orfa.nome,
                    "data": fmt(tema_data),
                },
            ]

        escrever(pasta / "catraca_presencas.csv", ["data", "matricula", "nome"], catraca)
        escrever(pasta / "justificativas.csv", ["data", "matricula", "aprovada"], justificativas)
        escrever(pasta / "p_mais_simulados.csv", cabecalho_p_mais, simulados)
        escrever(
            pasta / "corrija_me_redacoes.csv",
            ["data_tema", "tema", "matricula", "nome", "entregue"]
            + [f"c{i}" for i in range(1, 6)]
            + ["total"],
            redacoes,
        )
        resumo["anos"][str(ano)] = {
            "alunos": len(alunos),
            "turmas": tamanho.turmas,
            "dias_letivos": len(cal.dias_letivos),
            "ciclos": len(cal.ciclos),
            "temas_redacao": len(cal.temas),
        }

    caminho = destino / "perfis_conhecidos.json"
    caminho.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resumo


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tamanho", choices=TAMANHOS, default="pequena")
    parser.add_argument("--semente", type=int, default=SEMENTE_PADRAO)
    parser.add_argument(
        "--destino",
        type=Path,
        help="Pasta de saída (padrão: tests/dados_sinteticos/<tamanho>/).",
    )
    args = parser.parse_args(argv)
    destino = args.destino or DESTINO_PADRAO / args.tamanho
    resumo = gerar(destino, TAMANHOS[args.tamanho], args.semente)
    total = sum(a["alunos"] for a in resumo["anos"].values())
    print(f"Base '{args.tamanho}' gerada em {destino} ({total} alunos, semente {args.semente}).")


if __name__ == "__main__":
    main()
