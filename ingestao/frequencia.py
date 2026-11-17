"""Importação da frequência pela grade "Presença Anual" do CASD (RF003, RN001, RN002, RN003,
RN004, RN005, NF006, NF008, NF009).

A grade é a planilha que a equipe mantém a partir das abas diárias da catraca
(`Controle de Presença AAAA.xlsx`, `ingestao.planilhas_casd`): uma linha por aluno e uma
coluna por dia, com P (presente), F (falta: sem registro na catraca, RN001), J (falta
justificada, RN002) ou S (sem aula). A associação é pela coluna `Matrícula`, que a equipe
acrescentou à grade (RN003).

- Cada P, F ou J em dia letivo (`core.calendario.dias_letivos`, RN005) e na janela do aluno
  (do ingresso à saída, RN004) vira um `RegistroFrequencia`. A grade manda: P grava presente,
  F grava falta sem justificativa e J grava falta justificada.
- S (sem aula) não vira registro; P, F ou J em dia que o calendário do FAROL não considera
  letivo também não, mas geram aviso por dia ("o calendário está atualizado?"), assim como S
  em dia letivo e dias letivos sem coluna na grade.
- Matrícula sem aluno: a linha vira `PendenciaImportacao` (RN003), com os códigos da linha.
  Depois de associada, a linha vale para o aluno escolhido nas reimportações seguintes.
- Reimportar (a grade é reenviada ao longo do ano) só altera o que mudou, com auditoria; o
  resumo mostra os registros já existentes, e confirmar é confirmar a substituição (NF008).
  Aluno ausente da grade não é tocado (NF007).

O resumo conta linhas de aluno: as linhas de título, de semana e de totais são puladas.
Mensagens sem nome; a matrícula só aparece nas linhas inconsistentes, que só o Diretor vê.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Max

from core.auditoria import registrar_alteracoes
from core.calendario import dias_letivos, eh_dia_letivo
from core.models import PendenciaImportacao, PeriodoLetivo, RegistroAlteracao, RegistroFrequencia
from ingestao import planilhas_casd
from ingestao.base import ResumoImportacao, transacao_de_importacao
from ingestao.leitura import ArquivoInvalidoError, ler_bruto, ler_data
from ingestao.pendencias import (
    RESOLVIDA,
    LocalizadorAlunos,
    aluno_da_linha,
    aplicador,
    registrar_pendencia,
)

Origem = PendenciaImportacao.Origem
REFERENCIA = "grade"  # uma pendência por linha da grade, estável entre reimportações
LOTE = 2000
MAX_COLUNAS_GRADE = 500  # ~200 dias letivos, mais as colunas de faltas por semana
_DIA_MES = re.compile(r"^(\d{1,2})/(\d{1,2})$")
_MATRICULA = {"matricula", "rm", "n matricula", "numero de matricula"}
_NOME = {"nome", "nome do aluno", "aluno", "nome completo"}


@dataclass
class Grade:
    """A grade lida: as datas das colunas de dia e as linhas de aluno."""

    datas: list[date]
    linhas: list[dict]
    colunas_de_outro_ano: int = 0
    codigos_desconhecidos: int = 0


def _matricula(valor) -> str:
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor if valor is not None else "").strip()


def _data_da_coluna(valor, ano: int) -> date | None:
    """Data do cabeçalho de uma coluna de dia: data do XLSX, `dd/mm/aaaa` ou `dd/mm` (ano
    letivo informado). Outras colunas (Faltas, % Presença) devolvem None."""
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    achado = _DIA_MES.match(texto)
    if achado:
        try:
            return date(ano, int(achado.group(2)), int(achado.group(1)))
        except ValueError:
            return None
    return ler_data(texto) if "/" in texto or "-" in texto else None


def ler_grade(arquivo, nome_arquivo, *, ano: int, aba: str | None = None) -> Grade:
    """Lê a aba da grade (por padrão, "Presença Anual"). O cabeçalho é a primeira das dez
    linhas iniciais com as colunas Nome e Matrícula."""
    bruto = ler_bruto(arquivo, nome_arquivo, aba=aba or None, max_colunas=MAX_COLUNAS_GRADE)
    inicio = None
    for indice, linha in enumerate(bruto[:10]):
        nomes = {planilhas_casd.chave(c) for c in linha}
        if nomes & _NOME and nomes & _MATRICULA:
            inicio = indice
            break
    if inicio is None:
        raise ArquivoInvalidoError(
            "Cabeçalho não encontrado: a grade precisa das colunas Nome e Matrícula "
            "(acrescente a coluna Matrícula à planilha, RN003)."
        )
    cabecalho = bruto[inicio]
    chaves = [planilhas_casd.chave(c) for c in cabecalho]
    col_nome = next(i for i, c in enumerate(chaves) if c in _NOME)
    col_matricula = next(i for i, c in enumerate(chaves) if c in _MATRICULA)
    colunas, outro_ano = {}, 0
    for indice, valor in enumerate(cabecalho):
        dia = _data_da_coluna(valor, ano)
        if dia is None:
            continue
        if dia.year != ano:
            outro_ano += 1
            continue
        colunas[indice] = dia
    if not colunas:
        raise ArquivoInvalidoError("A grade não tem colunas de dia do ano letivo informado.")

    grade = Grade(datas=sorted(set(colunas.values())), linhas=[], colunas_de_outro_ano=outro_ano)
    for numero, valores in enumerate(bruto[inicio + 1 :], start=inicio + 2):

        def celula(i, valores=valores):
            return valores[i] if i < len(valores) else None

        codigos = {}
        for indice, dia in colunas.items():
            codigo = str(celula(indice) or "").strip().upper()
            if codigo in planilhas_casd.CODIGOS_PRESENCA:
                codigos[dia] = codigo
            elif codigo and codigo != "-":
                grade.codigos_desconhecidos += 1
        matricula = _matricula(celula(col_matricula))
        nome = str(celula(col_nome) or "").strip()
        if not matricula and not (nome and any(c in "PFJ" for c in codigos.values())):
            continue  # título, total, média ou linha vazia: toda linha de aluno tem nome
        grade.linhas.append(
            {"_linha": numero, "matricula": matricula, "nome": nome, "codigos": codigos}
        )
    if not grade.linhas:
        raise ArquivoInvalidoError("A grade não tem linhas de aluno.")
    return grade


def exemplo(ano: int) -> bytes:
    """Modelo para download: a grade no layout real, com duas linhas sintéticas (NF017)."""
    aa = ano % 100
    alunos = [
        {"nome": "Aluno Exemplo Um", "matricula": f"S{aa}0001", "turma": "Turma 1"},
        {"nome": "Aluno Exemplo Dois", "matricula": f"S{aa}0002", "turma": "Turma 2"},
    ]
    segunda = date(ano, 3, 2) - timedelta(days=date(ano, 3, 2).weekday())
    codigos = {}
    for n in range(5):
        dia = segunda + timedelta(days=n)
        codigos[(f"S{aa}0001", dia)] = "P"
        codigos[(f"S{aa}0002", dia)] = "PFJPS"[n]
    return planilhas_casd.grade_presenca(ano, alunos, codigos)


@dataclass
class ResumoFrequencia(ResumoImportacao):
    """`criados`, `atualizados` e `sem_alteracao` contam linhas de aluno (aluno novo na
    grade, com alteração ou sem); os `registros_*` contam registros de frequência (aluno e dia)."""

    registros_criados: int = 0
    registros_alterados: int = 0
    registros_iguais: int = 0
    presencas: int = 0
    faltas: int = 0
    justificadas: int = 0
    justificativas_mantidas: int = 0  # F da grade sobre falta já justificada no FAROL (D5)
    dias_letivos: int = 0
    inicio: date | None = None
    fim: date | None = None
    calendario_ate: date | None = None
    nao_letivos: list[tuple[date, int]] = field(default_factory=list)

    def assinatura(self) -> list[int]:
        return super().assinatura() + [
            self.registros_criados,
            self.registros_alterados,
            self.presencas,
            self.faltas,
            self.justificadas,
            self.justificativas_mantidas,
        ]


def _no_aluno(aluno, dia) -> bool:
    """O dia está entre o ingresso (RN004) e a saída do aluno?"""
    return aluno.data_ingresso <= dia and (aluno.data_saida is None or dia <= aluno.data_saida)


def _valores(codigo) -> tuple[bool, bool]:
    """(presente, justificada) de um código P, F ou J."""
    return codigo == "P", codigo == "J"


def _mantem_justificada(codigo, registro) -> bool:
    """D5 (pergunta B1, provisória): o F da grade não desfaz a justificativa já registrada no
    FAROL (RF008); vale como J. Para a grade mandar sempre, devolva False aqui e troque o aviso
    de `_avisar` por um que conte as justificadas que voltarão a falta."""
    return codigo == "F" and registro is not None and registro.justificada


def importar_frequencia(grade: Grade, *, ano: int, autor, gravar: bool):
    resumo = ResumoFrequencia()
    with transacao_de_importacao(gravar):
        resumo.inicio, resumo.fim = grade.datas[0], grade.datas[-1]
        letivos = set(dias_letivos(resumo.inicio, resumo.fim))
        resumo.dias_letivos = len(letivos)
        resumo.calendario_ate = PeriodoLetivo.objects.aggregate(f=Max("fim"))["f"]
        localizador = LocalizadorAlunos([linha["matricula"] for linha in grade.linhas], ano)
        linhas_de_aluno, vistos = [], set()
        for linha in grade.linhas:
            numero, matricula = linha["_linha"], linha["matricula"]
            aluno, motivo = aluno_da_linha(
                localizador,
                origem=Origem.FREQUENCIA,
                ano=ano,
                matricula=matricula,
                nome=linha["nome"],
                referencia=REFERENCIA,
            )
            if aluno is None and motivo == RESOLVIDA:
                resumo.sem_alteracao += 1  # pendência descartada pelo Diretor
                continue
            if aluno is None:
                registrar_pendencia(
                    origem=Origem.FREQUENCIA,
                    motivo=motivo,
                    ano=ano,
                    data=min(linha["codigos"], default=resumo.inicio),
                    matricula=matricula,
                    nome=linha["nome"],
                    referencia=REFERENCIA,
                    dados={"codigos": {d.isoformat(): c for d, c in linha["codigos"].items()}},
                )
                resumo.pendencias.append((numero, PendenciaImportacao.Motivo(motivo).label))
                continue
            if aluno.pk in vistos:
                resumo.inconsistentes.append((numero, matricula[:30], "aluno repetido na grade"))
                continue
            vistos.add(aluno.pk)
            linhas_de_aluno.append((aluno, linha["codigos"]))
        contagens = _apurar(resumo, linhas_de_aluno, letivos, autor)
        _avisar(resumo, grade, letivos, *contagens)
    return resumo


def _apurar(resumo, linhas_de_aluno, letivos, autor):
    """Cria ou altera um registro por aluno e dia com P, F ou J (em lote, NF011)."""
    existentes = {
        (r.aluno_id, r.data): r
        for r in RegistroFrequencia.objects.filter(
            aluno__in=[a for a, _ in linhas_de_aluno],
            data__gte=resumo.inicio,
            data__lte=resumo.fim,
        )
    }
    novos, alterados, auditoria = [], [], []
    s_letivo, nao_letivo, fora = Counter(), Counter(), 0
    for aluno, codigos in linhas_de_aluno:
        criou = mudou = havia = False
        for dia, codigo in sorted(codigos.items()):
            if codigo == "S":
                if dia in letivos and _no_aluno(aluno, dia):
                    s_letivo[dia] += 1
                continue
            if dia not in letivos:
                nao_letivo[dia] += 1
                continue
            if not _no_aluno(aluno, dia):
                fora += 1
                continue
            registro = existentes.get((aluno.pk, dia))
            if _mantem_justificada(codigo, registro):
                codigo = "J"
                resumo.justificativas_mantidas += 1
            presente, justificada = _valores(codigo)
            resumo.presencas += presente
            resumo.justificadas += justificada
            resumo.faltas += not presente and not justificada
            if registro is None:
                novos.append(
                    RegistroFrequencia(
                        aluno=aluno, data=dia, presente=presente, justificada=justificada
                    )
                )
                resumo.registros_criados += 1
                criou = True
                continue
            havia = True
            antes = {"presente": registro.presente, "justificada": registro.justificada}
            depois = {"presente": presente, "justificada": justificada}
            if antes == depois:
                resumo.registros_iguais += 1
                continue
            for campo, valor in depois.items():
                setattr(registro, campo, valor)
                if antes[campo] != valor:
                    auditoria.append(
                        RegistroAlteracao(
                            autor=autor,
                            modelo=RegistroFrequencia._meta.label_lower,
                            objeto_id=str(registro.pk),
                            campo=campo,
                            valor_anterior=str(antes[campo]),
                            valor_novo=str(valor),
                        )
                    )
            alterados.append(registro)
            resumo.registros_alterados += 1
            mudou = True
        if criou and not havia:
            resumo.criados += 1
        elif criou or mudou:
            resumo.atualizados += 1
        else:
            resumo.sem_alteracao += 1
    if existentes:
        resumo.sobreposicoes.append(
            f"{len(existentes)} registro(s) de frequência destes alunos já existem entre "
            f"{resumo.inicio:%d/%m/%Y} e {resumo.fim:%d/%m/%Y}; confirmar substitui "
            f"{resumo.registros_alterados} deles pelo que está na grade"
        )
    RegistroFrequencia.objects.bulk_create(novos, batch_size=LOTE)
    RegistroFrequencia.objects.bulk_update(alterados, ["presente", "justificada"], batch_size=LOTE)
    RegistroAlteracao.objects.bulk_create(auditoria, batch_size=LOTE)
    return s_letivo, nao_letivo, fora


def _avisar(resumo, grade, letivos, s_letivo, nao_letivo, fora):
    for dia in sorted(nao_letivo):
        resumo.nao_letivos.append((dia, nao_letivo[dia]))
        resumo.avisos.append(
            (
                0,
                f"{dia:%d/%m/%Y}: dia não letivo no calendário com {nao_letivo[dia]} "
                "registro(s) P, F ou J na grade; o calendário está atualizado?",
            )
        )
    for dia in sorted(s_letivo):
        resumo.avisos.append(
            (
                0,
                f"{dia:%d/%m/%Y}: dia letivo no calendário, mas a grade marca S (sem aula) "
                f"para {s_letivo[dia]} aluno(s)",
            )
        )
    if resumo.justificativas_mantidas:
        resumo.avisos.append(
            (
                0,
                f"{resumo.justificativas_mantidas} falta(s) já justificada(s) no FAROL aparecem "
                "como F na grade e continuam justificadas; para retirar a justificativa, use a "
                "tela de faltas do aluno",
            )
        )
    if fora:
        resumo.avisos.append(
            (0, f"{fora} registro(s) antes do ingresso ou depois da saída do aluno")
        )
    sem_coluna = letivos - set(grade.datas)
    if sem_coluna:
        resumo.avisos.append(
            (0, f"{len(sem_coluna)} dia(s) letivo(s) do calendário sem coluna na grade")
        )
    if grade.codigos_desconhecidos:
        resumo.avisos.append(
            (
                0,
                f"{grade.codigos_desconhecidos} célula(s) de dia com código desconhecido "
                "(use P, F, J ou S); ignoradas",
            )
        )
    if grade.colunas_de_outro_ano:
        resumo.avisos.append(
            (0, f"{grade.colunas_de_outro_ano} coluna(s) de dia de outro ano letivo ignoradas")
        )
    if resumo.calendario_ate is None:
        resumo.avisos.append((0, "nenhum período letivo cadastrado: não há dias letivos"))
    elif resumo.calendario_ate < resumo.fim:
        resumo.avisos.append(
            (
                0,
                f"calendário definido até {resumo.calendario_ate:%d/%m/%Y}: dias depois "
                "disso não entram",
            )
        )


@aplicador(Origem.FREQUENCIA)
def aplicar_pendencia(pendencia, aluno, autor) -> str:
    """Associar é gravar os P, F e J da linha da grade para o aluno escolhido."""
    aplicados = 0
    for iso, codigo in sorted(pendencia.dados.get("codigos", {}).items()):
        dia = date.fromisoformat(iso)
        if codigo == "S" or not _no_aluno(aluno, dia) or not eh_dia_letivo(dia):
            continue
        registro = RegistroFrequencia.objects.filter(aluno=aluno, data=dia).first()
        presente, justificada = _valores("J" if _mantem_justificada(codigo, registro) else codigo)
        if registro is None:
            RegistroFrequencia.objects.create(
                aluno=aluno, data=dia, presente=presente, justificada=justificada
            )
        elif (registro.presente, registro.justificada) != (presente, justificada):
            anteriores = {"presente": registro.presente, "justificada": registro.justificada}
            registro.presente, registro.justificada = presente, justificada
            registro.save(update_fields=["presente", "justificada"])
            registrar_alteracoes(autor=autor, objeto=registro, anteriores=anteriores)
        aplicados += 1
    if not aplicados:
        return "nenhum dia da linha é letivo e da janela do aluno"
    return ""
