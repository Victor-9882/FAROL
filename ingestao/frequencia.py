"""Importação da frequência da catraca (RF003, RN001, RN002, RN003, RN004, RN005, NF006, NF008).

O arquivo tem uma linha por **passagem** na catraca (`data`, `matricula`, `nome` opcional).
O Diretor informa o período; para cada aluno do ano e cada dia letivo do período, grava um
`RegistroFrequencia`: presente se houve passagem, ausente se não houve (RN001: falta é a
ausência de registro, sem tolerância de atraso).

- Dia letivo: `core.calendario.dias_letivos`, na hora do cálculo (RN005). Passagem em dia não
  letivo não vira registro, mas gera aviso por dia ("calendário desatualizado?").
- Aluno conta a partir do ingresso (RN004) e até a saída; aluno `INVALIDO` não conta.
- Matrícula sem aluno: a linha vira `PendenciaImportacao` (RN003). Pendência já associada a
  um aluno conta como passagem dele na reimportação.
- Reimportar o período substitui `presente` dos registros existentes, com auditoria (NF009),
  e nunca mexe em `justificada` (RN002). Os registros já existentes aparecem no resumo como
  sobreposição: confirmar a conferência é confirmar a substituição (NF008).

O resumo fecha com as linhas do arquivo: passagens usadas + ignoradas + inconsistentes +
pendências. Mensagens sem nome; a matrícula só aparece nas linhas inconsistentes, que só o
Diretor vê.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from django.conf import settings
from django.db.models import Max, Q

from core.auditoria import registrar_alteracoes
from core.calendario import dias_letivos, eh_dia_letivo
from core.models import (
    Aluno,
    PendenciaImportacao,
    PeriodoLetivo,
    RegistroAlteracao,
    RegistroFrequencia,
)
from ingestao.base import ResumoImportacao, transacao_de_importacao
from ingestao.cadastro import _chave_nome
from ingestao.leitura import ler_data
from ingestao.pendencias import RESOLVIDA, LocalizadorAlunos, aplicador, registrar_pendencia

Origem = PendenciaImportacao.Origem

COLUNAS = {
    "data": ("dia", "data_passagem", "data_hora"),
    "matricula": ("rm", "matricula_aluno"),
    "nome": ("aluno", "nome_completo"),
}
OPCIONAIS = frozenset({"nome"})
LOTE = 2000


def exemplos(ano: int) -> list[dict]:
    """Linhas sintéticas do modelo para download, no ano letivo pedido (NF017)."""
    aa = ano % 100
    return [
        {"data": f"02/03/{ano}", "matricula": f"S{aa}0001", "nome": "Aluno Exemplo Um"},
        {"data": f"02/03/{ano}", "matricula": f"S{aa}0002", "nome": "Aluno Exemplo Dois"},
    ]


def limite_linhas() -> int:
    """A catraca exporta uma linha por passagem: o limite é maior que o das outras planilhas."""
    return settings.IMPORTACAO_LIMITE_LINHAS_CATRACA


@dataclass
class ResumoFrequencia(ResumoImportacao):
    """`criados`, `atualizados` e `sem_alteracao` contam registros de frequência (aluno e dia);
    `importados` e `ignorados` contam linhas (passagens), para o total fechar com o arquivo."""

    passagens: int = 0
    passagens_ignoradas: int = 0
    presencas: int = 0
    faltas: int = 0
    dias_letivos: int = 0
    calendario_ate: date | None = None
    alunos: int = 0
    nao_letivos: list[tuple[date, int]] = field(default_factory=list)

    @property
    def importados(self) -> int:
        return self.passagens

    @property
    def ignorados(self) -> int:
        return self.passagens_ignoradas

    def assinatura(self) -> list[int]:
        return super().assinatura() + [
            self.passagens,
            self.passagens_ignoradas,
            self.presencas,
            self.faltas,
        ]


def _data(valor) -> date | None:
    """Aceita também `dd/mm/aaaa hh:mm[:ss]` (a catraca pode exportar a hora)."""
    if isinstance(valor, str) and " " in valor.strip():
        valor = valor.strip().split()[0]
    return ler_data(valor)


def _no_aluno(aluno, dia) -> bool:
    """O dia está entre o ingresso (RN004) e a saída do aluno?"""
    return aluno.data_ingresso <= dia and (aluno.data_saida is None or dia <= aluno.data_saida)


def importar_frequencia(linhas, *, ano: int, inicio: date, fim: date, autor, gravar: bool):
    resumo = ResumoFrequencia()
    with transacao_de_importacao(gravar):
        letivos = dias_letivos(inicio, fim)
        conjunto_letivos = set(letivos)
        resumo.dias_letivos = len(letivos)
        resumo.calendario_ate = PeriodoLetivo.objects.aggregate(f=Max("fim"))["f"]
        localizador = LocalizadorAlunos([linha.get("matricula") for linha in linhas], ano)
        presencas: set[tuple[str, date]] = set()
        vistas_pendencias: set[tuple[str, str, date]] = set()
        nao_letivos: Counter = Counter()
        primeira_linha: dict[date, int] = {}
        fora_do_aluno = 0

        for linha in linhas:
            numero = linha["_linha"]
            matricula = str(linha.get("matricula") or "").strip()

            def recusar(motivo, numero=numero, matricula=matricula):
                resumo.inconsistentes.append((numero, matricula[:30], motivo))

            if linha.get("data") in (None, ""):
                recusar("data em branco")
                continue
            dia = _data(linha.get("data"))
            if dia is None:
                recusar("data inválida (use dd/mm/aaaa ou aaaa-mm-dd)")
                continue
            if not inicio <= dia <= fim:
                recusar("data fora do período informado")
                continue
            if dia not in conjunto_letivos:
                nao_letivos[dia] += 1
                primeira_linha.setdefault(dia, numero)
                resumo.passagens_ignoradas += 1
                continue
            aluno, motivo = localizador.localizar(matricula)
            if aluno is None:
                nome = linha.get("nome") or ""
                chave = (matricula, _chave_nome(nome), dia)
                if chave in vistas_pendencias:
                    resumo.passagens_ignoradas += 1  # outra passagem da mesma pessoa no dia
                    continue
                vistas_pendencias.add(chave)
                situacao = registrar_pendencia(
                    origem=Origem.FREQUENCIA,
                    motivo=motivo,
                    ano=ano,
                    data=dia,
                    matricula=matricula,
                    nome=nome,
                    referencia=dia.isoformat(),
                    dados={"data": dia.isoformat()},
                )
                if situacao == RESOLVIDA:
                    resumo.passagens_ignoradas += 1
                else:
                    rotulo = PendenciaImportacao.Motivo(motivo).label
                    resumo.pendencias.append((numero, rotulo))
                continue
            if not _no_aluno(aluno, dia):
                fora_do_aluno += 1
                resumo.passagens_ignoradas += 1
                continue
            if (aluno.pk, dia) in presencas:
                resumo.passagens_ignoradas += 1  # várias passagens no dia: uma presença
                continue
            presencas.add((aluno.pk, dia))
            resumo.passagens += 1

        for dia in sorted(nao_letivos):
            resumo.nao_letivos.append((dia, nao_letivos[dia]))
            resumo.avisos.append(
                (
                    primeira_linha[dia],
                    f"{dia:%d/%m/%Y}: dia não letivo com {nao_letivos[dia]} passagem(ns); "
                    "o calendário está atualizado?",
                )
            )
        if fora_do_aluno:
            resumo.avisos.append(
                (0, f"{fora_do_aluno} passagem(ns) antes do ingresso ou depois da saída do aluno")
            )
        if resumo.calendario_ate is None:
            resumo.avisos.append((0, "nenhum período letivo cadastrado: não há dias letivos"))
        elif resumo.calendario_ate < fim:
            resumo.avisos.append(
                (
                    0,
                    f"calendário definido até {resumo.calendario_ate:%d/%m/%Y}: dias depois "
                    "disso não têm frequência apurada",
                )
            )

        associadas = PendenciaImportacao.objects.filter(
            origem=Origem.FREQUENCIA,
            situacao=PendenciaImportacao.Situacao.ASSOCIADA,
            data__gte=inicio,
            data__lte=fim,
        ).values_list("aluno_id", "data")
        presencas.update(associadas)
        _apurar(resumo, presencas, letivos, ano, inicio, fim, autor)
    return resumo


def _apurar(resumo, presencas, letivos, ano, inicio, fim, autor):
    """Cria ou substitui um registro por aluno e dia letivo do período (em lote)."""
    alunos = list(
        Aluno.objects.filter(turma__ano=ano, data_ingresso__lte=fim)
        .exclude(situacao=Aluno.Situacao.INVALIDO)
        .filter(Q(data_saida__isnull=True) | Q(data_saida__gte=inicio))
    )
    resumo.alunos = len(alunos)
    existentes = {
        (r.aluno_id, r.data): r
        for r in RegistroFrequencia.objects.filter(
            aluno__in=alunos, data__gte=inicio, data__lte=fim
        )
    }
    novos, alterados, auditoria = [], [], []
    for aluno in alunos:
        for dia in letivos:
            if not _no_aluno(aluno, dia):
                continue
            presente = (aluno.pk, dia) in presencas
            if presente:
                resumo.presencas += 1
            else:
                resumo.faltas += 1
            registro = existentes.get((aluno.pk, dia))
            if registro is None:
                novos.append(RegistroFrequencia(aluno=aluno, data=dia, presente=presente))
                resumo.criados += 1
            elif registro.presente != presente:
                registro.presente = presente
                alterados.append(registro)
                auditoria.append(
                    RegistroAlteracao(
                        autor=autor,
                        modelo=RegistroFrequencia._meta.label_lower,
                        objeto_id=str(registro.pk),
                        campo="presente",
                        valor_anterior=str(not presente),
                        valor_novo=str(presente),
                    )
                )
                resumo.atualizados += 1
            else:
                resumo.sem_alteracao += 1
    if existentes:
        resumo.sobreposicoes.append(
            f"{len(existentes)} registro(s) de frequência já existem entre {inicio:%d/%m/%Y} e "
            f"{fim:%d/%m/%Y}; confirmar substitui a presença de {resumo.atualizados} deles "
            "(ausências justificadas continuam justificadas)"
        )
    RegistroFrequencia.objects.bulk_create(novos, batch_size=LOTE)
    RegistroFrequencia.objects.bulk_update(alterados, ["presente"], batch_size=LOTE)
    RegistroAlteracao.objects.bulk_create(auditoria, batch_size=LOTE)


@aplicador(Origem.FREQUENCIA)
def aplicar_pendencia(pendencia, aluno, autor) -> str:
    """Associar uma passagem é marcar o aluno presente naquele dia (RN001)."""
    dia = date.fromisoformat(pendencia.dados["data"])
    if not _no_aluno(aluno, dia):
        return "a passagem é de antes do ingresso ou depois da saída do aluno"
    if not eh_dia_letivo(dia):
        return "o dia da passagem não é letivo no calendário"
    registro = RegistroFrequencia.objects.filter(aluno=aluno, data=dia).first()
    if registro is None:
        RegistroFrequencia.objects.create(aluno=aluno, data=dia, presente=True)
    elif not registro.presente:
        registro.presente = True
        registro.save(update_fields=["presente"])
        registrar_alteracoes(autor=autor, objeto=registro, anteriores={"presente": False})
    return ""
