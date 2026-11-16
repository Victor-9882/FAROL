"""Relatório dos alunos beneficiados por auxílios (RF021, SM #80, opção A).

A lista de beneficiados chega a cada uso, numa planilha só com matrículas, e é usada só
em memória: este módulo não grava nada (nem a lista, nem o tipo de auxílio, nem pendência
para matrícula sem aluno, nem trilha de importação). Ser beneficiado é dado socioeconômico,
fora do escopo de tratamento do sistema (FAROL_Contexto, "não fará"); por isso o fato nunca
vira registro. Mesmo período de referência e mesmas regras do painel (`inteligencia.painel`).

O bloco agregado (`Grupo`) não tem nome nem matrícula e é o que vai para a prestação de
contas; a lista nominal (`LinhaAluno`) é separada e só o Diretor a vê (RN013).
"""

from collections import Counter
from dataclasses import dataclass, field

from core.models import Intervencao
from ingestao.cadastro import validar_matricula
from inteligencia import consultas, painel
from inteligencia import indicadores as ind

COLUNAS = {"matricula": ("rm", "matricula_aluno")}
EXEMPLOS = [{"matricula": "S260001"}, {"matricula": "S260002"}]
SEM_DESFECHO = "Sem desfecho registrado"
DESFECHOS = [*(rotulo for _, rotulo in Intervencao.Desfecho.choices), SEM_DESFECHO]
CLASSES = {ind.QUEDA: "queda", ind.EVOLUCAO: "evolucao", ind.ESTAGNADO: "estagnado"}
CATEGORIAS = [(chave, painel.CATEGORIAS[chave]) for chave in ("queda", "estagnado", "evolucao")] + [
    ("sem_avaliacao", painel.CATEGORIAS["sem_avaliacao"])
]


@dataclass
class LinhaAluno:
    """Um aluno com os números do período. Dado nominal: só na lista do Diretor."""

    aluno: object
    frequencia: ind.Frequencia
    participacao: ind.Participacao
    categoria: str  # chave de `CATEGORIAS`
    alertas: int
    intervencoes: int

    @property
    def rotulo_categoria(self) -> str:
        return painel.CATEGORIAS[self.categoria]


@dataclass
class Grupo:
    """Números agregados de um grupo de alunos, sem nome nem matrícula."""

    rotulo: str
    alunos: int = 0
    frequencia: ind.Frequencia = field(default_factory=ind.Frequencia)
    participacao: ind.Participacao = field(default_factory=ind.Participacao)
    classificacao: Counter = field(default_factory=Counter)
    alunos_com_alerta: int = 0
    intervencoes: Counter = field(default_factory=Counter)

    @property
    def total_intervencoes(self) -> int:
        return sum(self.intervencoes.values())


@dataclass
class Relatorio:
    ref: painel.Referencia
    beneficiados: Grupo
    demais: Grupo
    nominal: list[LinhaAluno]
    lidas: int  # matrículas distintas e válidas do arquivo
    sem_aluno: int  # só a contagem: nunca vira pendência (SM #80)
    recusadas: list[tuple[int, str]]  # (linha, motivo), sem conteúdo de célula


def matriculas_do_arquivo(linhas, ano: int) -> tuple[set[str], list[tuple[int, str]]]:
    """Matrículas válidas e distintas do ano e as linhas recusadas (só número e motivo)."""
    validas: set[str] = set()
    recusadas: list[tuple[int, str]] = []
    for linha in linhas:
        matricula = str(linha.get("matricula") or "").strip()
        if not matricula:
            recusadas.append((linha["_linha"], "matrícula em branco"))
        elif motivo := validar_matricula(matricula, ano):
            recusadas.append((linha["_linha"], motivo))
        elif matricula in validas:
            recusadas.append((linha["_linha"], "matrícula repetida no arquivo"))
        else:
            validas.add(matricula)
    return validas, recusadas


def _grupo(rotulo, linhas, desfechos) -> Grupo:
    grupo = Grupo(rotulo=rotulo, alunos=len(linhas))
    for linha in linhas:
        grupo.frequencia += linha.frequencia
        grupo.participacao = ind.Participacao(
            grupo.participacao.registradas + linha.participacao.registradas,
            grupo.participacao.entregues + linha.participacao.entregues,
        )
        grupo.classificacao[linha.categoria] += 1
        grupo.alunos_com_alerta += 1 if linha.alertas else 0
        grupo.intervencoes.update(desfechos.get(linha.aluno.pk, []))
    return grupo


def calcular(matriculas: set[str], recusadas, ano: int) -> Relatorio:
    """Compara os beneficiados com os demais alunos do ano. Só lê o banco."""
    ref = painel.referencia(ano)
    alunos = list(consultas.alunos_do_ano(ano, ate=ref.fim))
    periodo = (ref.inicio, ref.fim) if ref.inicio else None
    frequencias = consultas.frequencias(alunos, *periodo) if periodo else {}
    participacoes = consultas.participacoes(alunos, *periodo) if periodo else {}
    historicos = consultas.historicos(alunos) if ref.ciclo else {}
    limiar = painel.limiar_desempenho()
    alertas = Counter(a.aluno_id for lista in painel.alertas_ativos(ref).values() for a in lista)
    rotulos = dict(Intervencao.Desfecho.choices)
    desfechos: dict[str, list[str]] = {}
    consulta = Intervencao.objects.filter(aluno__in=alunos).values_list("aluno_id", "desfecho")
    for aluno_id, desfecho in consulta:
        desfechos.setdefault(aluno_id, []).append(rotulos.get(desfecho, SEM_DESFECHO))
    linhas = []
    for aluno in alunos:
        categoria = "sem_avaliacao"
        if ref.ciclo and limiar:
            delta = ind.delta(ind.serie(historicos.get(aluno.pk, [])), ref.ciclo.pk)
            classe = ind.classificar(delta.valor if delta else None, limiar)
            categoria = CLASSES.get(classe, "sem_avaliacao")
        linhas.append(
            LinhaAluno(
                aluno=aluno,
                frequencia=frequencias.get(aluno.pk, ind.Frequencia()),
                participacao=participacoes.get(aluno.pk, ind.Participacao()),
                categoria=categoria,
                alertas=alertas.get(aluno.pk, 0),
                intervencoes=len(desfechos.get(aluno.pk, [])),
            )
        )
    nominal = sorted((x for x in linhas if x.aluno.pk in matriculas), key=lambda x: x.aluno.nome)
    demais = [x for x in linhas if x.aluno.pk not in matriculas]
    return Relatorio(
        ref=ref,
        beneficiados=_grupo("Beneficiados", nominal, desfechos),
        demais=_grupo("Demais alunos", demais, desfechos),
        nominal=nominal,
        lidas=len(matriculas),
        sem_aluno=len(matriculas) - len(nominal),
        recusadas=recusadas,
    )
