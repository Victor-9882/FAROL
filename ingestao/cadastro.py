"""Importação do cadastro de alunos e turmas (RF006, RN003, RN004, RN011, NF008).

Regras:
- A matrícula identifica o aluno (RN003). Importar nunca sobrescreve nome nem data de
  ingresso de aluno existente: a diferença vira divergência, resolvida na edição manual.
- Turma diferente da atual muda a turma preservando o histórico (RN011).
- Reimportar o mesmo arquivo não duplica nada (NF008).
- Aluno ausente do arquivo não é tocado (NF007). A situação do aluno nunca muda aqui.
Resultados e mensagens citam só linha, matrícula e motivo, nunca o nome (LGPD).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from django.db import transaction

from core.auditoria import registrar_alteracoes
from core.models import Aluno, Turma

COLUNAS = {
    "matricula": ("rm",),
    "nome": ("nome_completo", "aluno"),
    "turma": (),
    "data_ingresso": ("ingresso", "data_de_ingresso"),
}

# Pode faltar no arquivo ou vir vazia: vale o 1º de janeiro do ano letivo.
OPCIONAIS = frozenset({"data_ingresso"})

EXEMPLOS = [
    {"matricula": "S260001", "nome": "Aluno Exemplo Um", "turma": "Turma A",
     "data_ingresso": "02/02/2026"},
    {"matricula": "S260002", "nome": "Aluno Exemplo Dois", "turma": "Turma B",
     "data_ingresso": "02/02/2026"},
]  # fmt: skip

_MAX_NOME = Aluno._meta.get_field("nome").max_length
_MAX_TURMA = Turma._meta.get_field("nome").max_length


@dataclass
class ResumoCadastro:
    criados: int = 0
    mudancas_turma: int = 0
    sem_alteracao: int = 0
    turmas_criadas: int = 0
    divergencias: list[tuple[int, str, str]] = field(default_factory=list)
    inconsistentes: list[tuple[int, str, str]] = field(default_factory=list)


def _espacos(texto) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def _chave_nome(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", _espacos(texto)).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


def _data(valor) -> date | None:
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


# `AA` + modalidade (30 extensivo, 31 semiextensivo) + 3 dígitos; `AA` = ano letivo % 100.
MATRICULA_REAL = re.compile(r"^(\d{2})(30|31)\d{3}$")  # CASDvest
MATRICULA_SINTETICA = re.compile(r"^S(\d{2})\d{4}$")  # base sintética (NF017)


def validar_matricula(matricula: str, ano: int) -> str:
    """Devolve o motivo da recusa, ou "" se a matrícula é do padrão e do ano letivo."""
    achado = MATRICULA_REAL.match(matricula) or MATRICULA_SINTETICA.match(matricula)
    if achado is None:
        return "matrícula fora do padrão"
    if int(achado.group(1)) != ano % 100:
        return "matrícula de outro ano letivo"
    return ""


def _validar(linha, ano) -> tuple[dict | None, str]:
    matricula = str(linha.get("matricula") or "").strip()
    if not matricula:
        return None, "matrícula em branco"
    motivo = validar_matricula(matricula, ano)
    if motivo:
        return None, motivo
    nome = _espacos(linha.get("nome"))
    if not nome:
        return None, "nome em branco"
    if len(nome) > _MAX_NOME:
        return None, f"nome com mais de {_MAX_NOME} caracteres"
    turma = _espacos(linha.get("turma"))
    if not turma:
        return None, "turma em branco"
    if len(turma) > _MAX_TURMA:
        return None, f"turma com mais de {_MAX_TURMA} caracteres"
    bruta = linha.get("data_ingresso")
    informada = not (bruta is None or str(bruta).strip() == "")
    ingresso = _data(bruta) if informada else None
    if informada and ingresso is None:
        return None, "data de ingresso inválida (use dd/mm/aaaa ou aaaa-mm-dd)"
    return {
        "matricula": matricula,
        "nome": nome,
        "turma": turma,
        "ingresso": ingresso,
        "ingresso_padrao": date(ano, 1, 1),
    }, ""


def importar_cadastro(linhas, *, ano: int, autor, data_mudanca: date, gravar: bool):
    """Aplica `linhas` (de `ler_tabela`) ao cadastro. Com `gravar=False` só confere:
    devolve o mesmo resumo e desfaz tudo."""
    resumo = ResumoCadastro()
    with transaction.atomic():
        validas = []
        vistas = set()
        for linha in linhas:
            numero = linha["_linha"]
            dados, motivo = _validar(linha, ano)
            if dados is None:
                resumo.inconsistentes.append(
                    (numero, str(linha.get("matricula") or "").strip()[:30], motivo)
                )
            elif dados["matricula"] in vistas:
                resumo.inconsistentes.append(
                    (numero, dados["matricula"], "matrícula repetida no arquivo")
                )
            else:
                vistas.add(dados["matricula"])
                validas.append((numero, dados))

        existentes = Aluno.objects.in_bulk(list(vistas))
        turmas = {t.nome.casefold(): t for t in Turma.objects.filter(ano=ano)}

        def turma_de(nome):
            turma = turmas.get(nome.casefold())
            if turma is None:
                turma = turmas[nome.casefold()] = Turma.objects.create(nome=nome, ano=ano)
                resumo.turmas_criadas += 1
            return turma

        for numero, d in validas:
            aluno = existentes.get(d["matricula"])
            if aluno is None:
                Aluno(
                    matricula=d["matricula"],
                    nome=d["nome"],
                    data_ingresso=d["ingresso"] or d["ingresso_padrao"],
                    turma=turma_de(d["turma"]),
                ).save()
                resumo.criados += 1
                continue
            if _chave_nome(aluno.nome) != _chave_nome(d["nome"]):
                resumo.divergencias.append((numero, aluno.matricula, "nome diferente do cadastro"))
                continue
            if d["ingresso"] is not None and aluno.data_ingresso != d["ingresso"]:
                resumo.divergencias.append(
                    (numero, aluno.matricula, "data de ingresso diferente do cadastro")
                )
                continue
            atual = turmas.get(d["turma"].casefold())
            if atual is not None and atual.pk == aluno.turma_id:
                resumo.sem_alteracao += 1
                continue
            periodo = aluno.historico_turmas.get(data_fim__isnull=True)
            if data_mudanca <= periodo.data_inicio:
                resumo.inconsistentes.append(
                    (numero, aluno.matricula, "data da mudança não é posterior ao início da turma")
                )
                continue
            anterior = aluno.turma
            aluno.mudar_turma(turma_de(d["turma"]), data_mudanca)
            registrar_alteracoes(autor=autor, objeto=aluno, anteriores={"turma": anterior})
            resumo.mudancas_turma += 1

        if not gravar:
            transaction.set_rollback(True)
    return resumo
