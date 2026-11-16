"""Importação das redações do Corrija-me (RF005, RN003, RN004, RN007, NF006, NF008, NF009).

O arquivo tem uma linha por aluno e tema: `data_tema` (a terça-feira em que o tema foi
lançado, RN007), `tema` (título), `matricula`, `nome` (opcional), `entregue` (S/N), as cinco
competências `c1` a `c5` (0 a 200) e, opcional, o `total`.

- Tema: os temas são publicados no Corrija-me e não estão no calendário (`docs/dominio-casd.md`,
  seção 5). Por isso, a importação cria o `TemaRedacao` da terça que ainda não existe, com o
  título do arquivo. Se já existe com outro título, mantém o cadastrado e avisa.
- Não entregue: fica registrada com `entregue=False` e sem notas. Não entregue com nota, ou
  entregue sem alguma competência, é inconsistente. `total` diferente da soma também.
- Tema de antes do ingresso (a semana toda) ou depois da saída do aluno é inconsistente (RN004).
- Matrícula sem aluno (inclusive em branco, caso visto no export real) vira
  `PendenciaImportacao` (RN003).
- Reimportar atualiza o que mudou, com auditoria (NF009), e o resumo avisa quantas
  redações já existiam (NF008).

As mensagens nunca trazem nome nem nota.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from core.auditoria import registrar_alteracoes
from core.models import COMPETENCIAS_REDACAO, PendenciaImportacao, ResultadoRedacao, TemaRedacao
from ingestao.base import ResumoImportacao, linha_isolada, transacao_de_importacao
from ingestao.cadastro import _chave_nome
from ingestao.calendario import _booleano, _vazio
from ingestao.leitura import ler_data
from ingestao.pendencias import RESOLVIDA, LocalizadorAlunos, aplicador, registrar_pendencia

Origem = PendenciaImportacao.Origem
MAX_COMPETENCIA = 200
MAX_TEMA = 200
SEMANA = timedelta(days=6)

COLUNAS = {
    "data_tema": ("data", "terca", "semana", "data_do_tema"),
    "tema": ("titulo", "titulo_tema"),
    "matricula": ("rm", "matricula_aluno"),
    "nome": ("aluno", "nome_completo"),
    "entregue": ("entrega", "entregou"),
    **{f"c{n}": (f"competencia_{n}", f"nota_c{n}") for n in range(1, 6)},
    "total": ("nota_total", "nota"),
}
OPCIONAIS = frozenset({"nome", "tema", "total"})


def exemplos(ano: int) -> list[dict]:
    """Linhas sintéticas do modelo para download, no ano letivo pedido (NF017)."""
    aa = ano % 100
    terca = date(ano, 3, 3)
    while terca.weekday() != 1:
        terca += timedelta(days=1)
    base = {"data_tema": f"{terca:%d/%m/%Y}", "tema": "Tema de exemplo"}
    notas = {f"c{n}": 160 for n in range(1, 6)} | {"total": 800}
    vazio = {f"c{n}": "" for n in range(1, 6)} | {"total": ""}
    return [
        base | {"matricula": f"S{aa}0001", "nome": "Aluno Exemplo Um", "entregue": "S"} | notas,
        base | {"matricula": f"S{aa}0002", "nome": "Aluno Exemplo Dois", "entregue": "N"} | vazio,
    ]


@dataclass
class ResumoRedacoes(ResumoImportacao):
    """Conta linhas (aluno e tema): criada, atualizada ou sem alteração."""

    entregues: int = 0
    nao_entregues: int = 0
    temas_criados: int = 0

    def assinatura(self) -> list[int]:
        return super().assinatura() + [self.entregues, self.nao_entregues, self.temas_criados]


def _inteiro(valor) -> int | None:
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, int):
        return valor
    texto = str(valor).strip()
    return int(texto) if texto.isdigit() else None


def _titulo(valor) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def _validar(linha, ano) -> tuple[dict | None, str]:
    bruta = linha.get("data_tema")
    if _vazio(bruta):
        return None, "data do tema em branco"
    data = ler_data(bruta)
    if data is None:
        return None, "data do tema inválida (use dd/mm/aaaa ou aaaa-mm-dd)"
    if data.year != ano:
        return None, "data do tema fora do ano letivo informado"
    if data.weekday() != 1:
        return None, "a data do tema precisa ser uma terça-feira (RN007)"
    tema = _titulo(linha.get("tema"))
    if len(tema) > MAX_TEMA:
        return None, f"tema com mais de {MAX_TEMA} caracteres"
    entregue = None if _vazio(linha.get("entregue")) else _booleano(linha.get("entregue"))
    if entregue is None:
        return None, "entrega inválida (use S ou N)"
    brutas = [linha.get(f"c{n}") for n in range(1, 6)]
    total = linha.get("total")
    if not entregue:
        if not all(_vazio(v) for v in brutas) or not (_vazio(total) or _inteiro(total) == 0):
            return None, "redação não entregue com nota"
        return {"data": data, "tema": tema, "entregue": False, "notas": [None] * 5}, ""
    notas = []
    for n, valor in enumerate(brutas, 1):
        if _vazio(valor):
            return None, f"competência {n} em branco em redação entregue"
        nota = _inteiro(valor)
        if nota is None or not 0 <= nota <= MAX_COMPETENCIA:
            return None, f"competência {n} fora de 0 a {MAX_COMPETENCIA}"
        notas.append(nota)
    if not _vazio(total) and _inteiro(total) != sum(notas):
        return None, "total diferente da soma das competências"
    return {"data": data, "tema": tema, "entregue": True, "notas": notas}, ""


def _no_aluno(aluno, terca) -> bool:
    """O aluno estava no curso em algum dia da semana do tema (terça a segunda)?"""
    return aluno.data_ingresso <= terca + SEMANA and (
        aluno.data_saida is None or terca <= aluno.data_saida
    )


def _valores(tema, entregue, notas) -> dict:
    return {
        "tema": tema,
        "entregue": entregue,
        **dict(zip(COMPETENCIAS_REDACAO, notas, strict=True)),
    }


def _gravar(aluno, terca, valores, existente, autor) -> str:
    """Cria ou atualiza a redação. Devolve "criado", "atualizado" ou "igual"."""
    if existente is None:
        ResultadoRedacao.objects.create(aluno=aluno, tema_semana=terca, **valores)
        return "criado"
    anteriores = {c: getattr(existente, c) for c in valores}
    if all(anteriores[c] == v for c, v in valores.items()):
        return "igual"
    for campo, valor in valores.items():
        setattr(existente, campo, valor)
    existente.save(update_fields=list(valores))
    registrar_alteracoes(autor=autor, objeto=existente, anteriores=anteriores)
    return "atualizado"


class _Temas:
    """Temas do ano por terça; cria o que falta com o título do arquivo (RN007)."""

    def __init__(self, ano, resumo):
        self.resumo = resumo
        self.por_data = {t.data: t for t in TemaRedacao.objects.filter(data__year=ano)}
        self.avisados: set[date] = set()

    def tema(self, terca, titulo, numero) -> tuple[TemaRedacao | None, str]:
        existente = self.por_data.get(terca)
        if existente is None:
            if not titulo:
                return None, "tema em branco e não cadastrado para esta terça"
            existente = TemaRedacao.objects.create(data=terca, tema=titulo)
            self.por_data[terca] = existente
            self.resumo.temas_criados += 1
        elif titulo and _chave_nome(titulo) != _chave_nome(existente.tema):
            if terca not in self.avisados:
                self.avisados.add(terca)
                self.resumo.avisos.append(
                    (
                        numero,
                        f"{terca:%d/%m/%Y}: o tema do arquivo difere do cadastrado; "
                        "mantido o cadastrado",
                    )
                )
        return existente, ""


def importar_redacoes(linhas, *, ano: int, autor, gravar: bool):
    resumo = ResumoRedacoes()
    with transacao_de_importacao(gravar):
        temas = _Temas(ano, resumo)
        localizador = LocalizadorAlunos([linha.get("matricula") for linha in linhas], ano)
        validas, vistas = [], set()
        for linha in linhas:
            numero = linha["_linha"]
            matricula = str(linha.get("matricula") or "").strip()

            def recusar(motivo, numero=numero, matricula=matricula):
                resumo.inconsistentes.append((numero, matricula[:30], motivo))

            dados, motivo = _validar(linha, ano)
            if dados is None:
                recusar(motivo)
                continue
            tema, motivo = temas.tema(dados["data"], dados["tema"], numero)
            if tema is None:
                recusar(motivo)
                continue
            aluno, motivo = localizador.localizar(matricula)
            chave = (
                (aluno.pk, tema.data)
                if aluno
                else (matricula, _chave_nome(linha.get("nome")), tema.data)
            )
            if chave in vistas:
                recusar("aluno repetido no mesmo tema")
                continue
            vistas.add(chave)
            valores = _valores(tema.tema, dados["entregue"], dados["notas"])
            if aluno is None:
                _pendencia(resumo, numero, motivo, ano, tema, matricula, linha, valores)
                continue
            if not _no_aluno(aluno, tema.data):
                recusar("tema de antes do ingresso ou depois da saída do aluno (RN004)")
                continue
            validas.append((numero, aluno, tema, valores))

        existentes = {
            (r.aluno_id, r.tema_semana): r
            for r in ResultadoRedacao.objects.filter(
                aluno_id__in={a.pk for _, a, _, _ in validas},
                tema_semana__in={t.data for _, _, t, _ in validas},
            )
        }
        for numero, aluno, tema, valores in validas:

            def recusar(motivo, numero=numero, matricula=aluno.pk):
                resumo.inconsistentes.append((numero, matricula, motivo))

            with linha_isolada(recusar):
                situacao = _gravar(
                    aluno, tema.data, valores, existentes.get((aluno.pk, tema.data)), autor
                )
                if situacao == "criado":
                    resumo.criados += 1
                elif situacao == "atualizado":
                    resumo.atualizados += 1
                else:
                    resumo.sem_alteracao += 1
                if valores["entregue"]:
                    resumo.entregues += 1
                else:
                    resumo.nao_entregues += 1
        if existentes:
            resumo.sobreposicoes.append(
                f"{len(existentes)} redação(ões) deste arquivo já estavam importadas; "
                f"confirmar atualiza {resumo.atualizados} delas"
            )
    return resumo


def _pendencia(resumo, numero, motivo, ano, tema, matricula, linha, valores):
    situacao = registrar_pendencia(
        origem=Origem.REDACAO,
        motivo=motivo,
        ano=ano,
        data=tema.data,
        matricula=matricula,
        nome=linha.get("nome") or "",
        referencia=tema.data.isoformat(),
        dados={
            "tema_semana": tema.data.isoformat(),
            "entregue": valores["entregue"],
            "notas": [valores[c] for c in COMPETENCIAS_REDACAO],
        },
    )
    if situacao == RESOLVIDA:
        resumo.sem_alteracao += 1  # já associada ou descartada: nada a fazer
    else:
        resumo.pendencias.append((numero, PendenciaImportacao.Motivo(motivo).label))


@aplicador(Origem.REDACAO)
def aplicar_pendencia(pendencia, aluno, autor) -> str:
    """Associar é gravar a redação (entregue ou não) para o aluno escolhido."""
    terca = date.fromisoformat(pendencia.dados["tema_semana"])
    tema = TemaRedacao.objects.filter(data=terca).first()
    if tema is None:
        return "o tema da redação não está cadastrado"
    if not _no_aluno(aluno, terca):
        return "o tema é de antes do ingresso ou depois da saída do aluno"
    if ResultadoRedacao.objects.filter(aluno=aluno, tema_semana=terca).exists():
        return "o aluno já tem redação neste tema"
    valores = _valores(tema.tema, pendencia.dados["entregue"], pendencia.dados["notas"])
    _gravar(aluno, terca, valores, None, autor)
    return ""
