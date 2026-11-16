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
from datetime import date

from core.auditoria import registrar_alteracoes
from core.models import Aluno, Turma
from ingestao.base import ResumoImportacao, linha_isolada, transacao_de_importacao, triar
from ingestao.leitura import ler_data

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
class ResumoCadastro(ResumoImportacao):
    mudancas_turma: int = 0
    turmas_criadas: int = 0
    divergencias: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def importados(self) -> int:
        return self.criados + self.mudancas_turma

    @property
    def divergentes(self) -> int:
        return len(self.divergencias)

    def assinatura(self) -> list[int]:
        return super().assinatura() + [self.mudancas_turma, self.turmas_criadas]


def _espacos(texto) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def _chave_nome(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", _espacos(texto)).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


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
    ingresso = ler_data(bruta) if informada else None
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
    with transacao_de_importacao(gravar):
        validas = triar(
            linhas,
            lambda linha: _validar(linha, ano),
            chave=lambda d: d["matricula"],
            recusar=lambda linha, motivo: resumo.inconsistentes.append(
                (linha["_linha"], str(linha.get("matricula") or "").strip()[:30], motivo)
            ),
            repetida="matrícula repetida no arquivo",
        )
        vistas = {d["matricula"] for _, d in validas}
        existentes = Aluno.objects.in_bulk(list(vistas))
        turmas = {t.nome.casefold(): t for t in Turma.objects.filter(ano=ano)}

        def turma_de(nome):
            turma = turmas.get(nome.casefold())
            if turma is None:
                turma = turmas[nome.casefold()] = Turma.objects.create(nome=nome, ano=ano)
                resumo.turmas_criadas += 1
            return turma

        def aplicar(numero, d):
            aluno = existentes.get(d["matricula"])
            if aluno is None:
                Aluno(
                    matricula=d["matricula"],
                    nome=d["nome"],
                    data_ingresso=d["ingresso"] or d["ingresso_padrao"],
                    turma=turma_de(d["turma"]),
                ).save()
                resumo.criados += 1
                return
            if _chave_nome(aluno.nome) != _chave_nome(d["nome"]):
                resumo.divergencias.append((numero, aluno.matricula, "nome diferente do cadastro"))
                return
            if d["ingresso"] is not None and aluno.data_ingresso != d["ingresso"]:
                resumo.divergencias.append(
                    (numero, aluno.matricula, "data de ingresso diferente do cadastro")
                )
                return
            atual = turmas.get(d["turma"].casefold())
            if atual is not None and atual.pk == aluno.turma_id:
                resumo.sem_alteracao += 1
                return
            periodo = aluno.historico_turmas.get(data_fim__isnull=True)
            if data_mudanca <= periodo.data_inicio:
                resumo.inconsistentes.append(
                    (numero, aluno.matricula, "data da mudança não é posterior ao início da turma")
                )
                return
            anterior = aluno.turma
            aluno.mudar_turma(turma_de(d["turma"]), data_mudanca)
            registrar_alteracoes(autor=autor, objeto=aluno, anteriores={"turma": anterior})
            resumo.mudancas_turma += 1

        def recusador(numero, matricula):
            # NF006: se a linha for desfeita (savepoint), a turma que ela criou também some.
            turmas_antes, criadas_antes = dict(turmas), resumo.turmas_criadas

            def recusar(motivo):
                turmas.clear()
                turmas.update(turmas_antes)
                resumo.turmas_criadas = criadas_antes
                resumo.inconsistentes.append((numero, matricula, motivo))

            return recusar

        for numero, d in validas:
            with linha_isolada(recusador(numero, d["matricula"])):
                aplicar(numero, d)
    return resumo
