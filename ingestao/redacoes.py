"""Importação da exportação do Corrija-me (RF005, RN003, RN004, RN007, NF006, NF008, NF009).

A exportação (`ingestao.planilhas_casd`) tem uma linha por redação **entregue**: `RM`
(matrícula, RN003), `NOME COMPLETO`, `BANCA`, `TEMA`, `C1` a `C5`, `NOTAL FINAL` (sic),
`ID DA ATIVIDADE`, `DATA ENVIO` e outras colunas que o FAROL ignora. Ela não traz a data do
tema: o Diretor escolhe no formulário a terça-feira do tema (RN007).

- Tema: se ainda não há `TemaRedacao` nessa terça, ele é criado com o título mais frequente do
  arquivo (os temas são publicados no Corrija-me, `docs/dominio-casd.md`, seção 5). Se já há,
  o cadastrado é mantido e o resumo avisa quando o título difere.
- Escala pela banca: ENEM (ou banca em branco) exige as cinco competências, de 0 a 200, e a
  nota final, se vier, precisa ser a soma. Outras bancas (VUNESP) têm menos critérios e notas
  decimais: exige C1 a C4, e a nota final é a da banca.
- Não entregue: o aluno ativo do ano, no curso na semana do tema (RN004), que não aparece no
  arquivo ganha o registro `entregue=False`, sem nota. Registro já existente não é tocado.
- Reenvio (o mesmo aluno mais de uma vez): vale o envio mais recente; os demais são ignorados.
- Linha de outra atividade do Corrija-me (`ID DA ATIVIDADE` diferente do restante) ou de fora
  da janela do aluno é inconsistente.
- Matrícula em branco (caso visto no export real), fora do padrão ou sem aluno vira
  `PendenciaImportacao`; depois de associada, vale para o aluno escolhido.
- Reimportar atualiza o que mudou, com auditoria (NF009); o resumo avisa quantas redações já
  existiam (NF008).

As mensagens nunca trazem nome nem nota.
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Q

from core.auditoria import registrar_alteracoes
from core.models import (
    COMPETENCIAS_REDACAO,
    Aluno,
    PendenciaImportacao,
    ResultadoRedacao,
    TemaRedacao,
)
from ingestao import planilhas_casd
from ingestao.base import ResumoImportacao, linha_isolada, transacao_de_importacao
from ingestao.cadastro import _chave_nome
from ingestao.pendencias import (
    RESOLVIDA,
    LocalizadorAlunos,
    aluno_da_linha,
    aplicador,
    registrar_pendencia,
)

Origem = PendenciaImportacao.Origem
MAX_COMPETENCIA = Decimal("200")
MAX_FINAL = Decimal("1000")
TOLERANCIA_SOMA = Decimal("0.5")
SEMANA = timedelta(days=6)

COLUNAS = {
    "matricula": ("rm", "matricula_aluno"),
    "nome": ("nome_completo", "aluno"),
    "banca": (),
    "tema": (),
    **{f"c{n}": (f"competencia_{n}",) for n in range(1, 6)},
    "nota_final": ("notal_final", "nota_total"),
    "atividade": ("id_da_atividade",),
    "data_envio": ("data_de_envio",),
}
OPCIONAIS = frozenset({"nome", "banca", "tema", "c5", "nota_final", "atividade", "data_envio"})


def exemplo(ano: int) -> bytes:
    """Modelo para download: a exportação no layout real, com duas redações sintéticas
    (NF017), na banca ENEM usada pelo CASDvest."""
    aa = ano % 100
    envio = datetime(ano, 3, 5, 18, 30)
    base = {
        "atividade": 1,
        "envio": envio,
        "correcao": envio + timedelta(days=2),
        "banca": "ENEM",
        "tema": "Tema de exemplo",
        "turma": f"CASDvest {ano} - Turma 1",
    }
    return planilhas_casd.exportacao_corrija_me(
        [
            base
            | {
                "id": 1,
                "nome": "Aluno Exemplo Um",
                "rm": f"S{aa}0001",
                "notas": [160, 160, 160, 160, 160],
                "final": 800,
            },
            base
            | {
                "id": 2,
                "nome": "Aluno Exemplo Dois",
                "rm": f"S{aa}0002",
                "notas": [120, 160, 120, 160, 120],
                "final": 680,
            },
        ]  # fmt: skip
    )


@dataclass
class ResumoRedacoes(ResumoImportacao):
    """Conta linhas (redação entregue): criada, atualizada ou sem alteração. `reenvios` são
    linhas ignoradas; `nao_entregues` são alunos sem linha, que ganham o registro de não
    entrega (não são linhas do arquivo)."""

    reenvios: int = 0
    nao_entregues: int = 0
    temas_criados: int = 0

    @property
    def ignorados(self) -> int:
        return self.sem_alteracao + self.reenvios

    def assinatura(self) -> list[int]:
        return super().assinatura() + [self.reenvios, self.nao_entregues, self.temas_criados]


def _vazio(valor) -> bool:
    return valor is None or str(valor).strip() == ""


def _decimal(valor, casas="0.1") -> Decimal | None:
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except InvalidOperation:
        return None
    return numero.quantize(Decimal(casas)) if numero.is_finite() else None


def _titulo(valor) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()[:200]


def _envio(valor) -> datetime:
    if isinstance(valor, datetime):
        return valor
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valor or "").strip(), formato)
        except ValueError:
            continue
    return datetime.min


def _enem(banca) -> bool:
    return not _titulo(banca) or "enem" in planilhas_casd.chave(banca)


def _validar(linha) -> tuple[dict | None, str]:
    """Devolve os valores da redação entregue ou o motivo da recusa."""
    enem = _enem(linha.get("banca"))
    exigidas = 5 if enem else 4
    notas = []
    for n in range(1, 6):
        bruta = linha.get(f"c{n}")
        if _vazio(bruta):
            if n <= exigidas:
                return None, f"competência {n} em branco"
            notas.append(None)
            continue
        nota = _decimal(bruta)
        if nota is None or not 0 <= nota <= MAX_COMPETENCIA:
            return None, f"competência {n} fora de 0 a 200"
        notas.append(nota)
    final = None
    if not _vazio(linha.get("nota_final")):
        final = _decimal(linha.get("nota_final"), "0.01")
        if final is None or not 0 <= final <= MAX_FINAL:
            return None, "nota final fora de 0 a 1000"
        if enem and abs(final - sum(notas)) > TOLERANCIA_SOMA:
            return None, "nota final diferente da soma das competências"
    valores = {
        "entregue": True,
        "banca": _titulo(linha.get("banca"))[:80],
        "nota_final": final,
        **dict(zip(COMPETENCIAS_REDACAO, notas, strict=True)),
    }
    return valores, ""


def _no_aluno(aluno, terca) -> bool:
    """O aluno estava no curso em algum dia da semana do tema (terça a segunda)?"""
    return aluno.data_ingresso <= terca + SEMANA and (
        aluno.data_saida is None or terca <= aluno.data_saida
    )


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


def _tema(terca, linhas, resumo) -> TemaRedacao | None:
    titulos = Counter(_titulo(linha.get("tema")) for linha in linhas if _titulo(linha.get("tema")))
    titulo = titulos.most_common(1)[0][0] if titulos else ""
    tema = TemaRedacao.objects.filter(data=terca).first()
    if tema is None:
        if not titulo:
            return None
        resumo.temas_criados += 1
        return TemaRedacao.objects.create(data=terca, tema=titulo)
    if titulo and _chave_nome(titulo) != _chave_nome(tema.tema):
        resumo.avisos.append(
            (0, f"{terca:%d/%m/%Y}: o tema do arquivo difere do cadastrado; mantido o cadastrado")
        )
    return tema


def importar_redacoes(linhas, *, ano: int, terca: date, autor, gravar: bool):
    resumo = ResumoRedacoes()
    with transacao_de_importacao(gravar):
        tema = _tema(terca, linhas, resumo)
        if tema is None:
            for linha in linhas:
                resumo.inconsistentes.append(
                    (linha["_linha"], str(linha.get("matricula") or "")[:30],
                     "tema não cadastrado nesta terça e sem título no arquivo")
                )  # fmt: skip
            return resumo
        atividades = Counter(
            str(linha.get("atividade")) for linha in linhas if not _vazio(linha.get("atividade"))
        )
        principal = atividades.most_common(1)[0][0] if atividades else None
        localizador = LocalizadorAlunos([linha.get("matricula") for linha in linhas], ano)
        no_arquivo: set[str] = set()
        por_aluno: dict[str, tuple] = {}
        for linha in sorted(linhas, key=lambda li: _envio(li.get("data_envio")), reverse=True):
            numero = linha["_linha"]
            matricula = str(linha.get("matricula") or "").strip()
            no_arquivo.add(matricula)

            def recusar(motivo, numero=numero, matricula=matricula):
                resumo.inconsistentes.append((numero, matricula[:30], motivo))

            if principal and str(linha.get("atividade")) != principal:
                recusar("redação de outra atividade do Corrija-me (ID DA ATIVIDADE)")
                continue
            valores, motivo = _validar(linha)
            if valores is None:
                recusar(motivo)
                continue
            valores["tema"] = tema.tema
            aluno, motivo = aluno_da_linha(
                localizador,
                origem=Origem.REDACAO,
                ano=ano,
                matricula=matricula,
                nome=linha.get("nome") or "",
                referencia=terca.isoformat(),
            )
            if aluno is None and motivo == RESOLVIDA:
                resumo.sem_alteracao += 1  # pendência descartada pelo Diretor
                continue
            if aluno is None:
                _pendencia(resumo, numero, motivo, ano, terca, matricula, linha, valores)
                continue
            no_arquivo.add(aluno.pk)
            if aluno.pk in por_aluno:
                resumo.reenvios += 1  # vale o envio mais recente, já guardado
                continue
            if not _no_aluno(aluno, terca):
                recusar("tema de antes do ingresso ou depois da saída do aluno (RN004)")
                continue
            por_aluno[aluno.pk] = (numero, aluno, valores)

        existentes = {
            r.aluno_id: r
            for r in ResultadoRedacao.objects.filter(tema_semana=terca, aluno_id__in=por_aluno)
        }
        for numero, aluno, valores in por_aluno.values():

            def recusar(motivo, numero=numero, matricula=aluno.pk):
                resumo.inconsistentes.append((numero, matricula, motivo))

            with linha_isolada(recusar):
                situacao = _gravar(aluno, terca, valores, existentes.get(aluno.pk), autor)
                if situacao == "criado":
                    resumo.criados += 1
                elif situacao == "atualizado":
                    resumo.atualizados += 1
                else:
                    resumo.sem_alteracao += 1
        if existentes:
            resumo.sobreposicoes.append(
                f"{len(existentes)} redação(ões) deste tema já estavam registradas; "
                f"confirmar atualiza {resumo.atualizados} delas"
            )
        _nao_entregues(resumo, ano, terca, tema, no_arquivo)
    return resumo


def _nao_entregues(resumo, ano, terca, tema, no_arquivo):
    """Aluno do ano, no curso na semana do tema, sem linha no arquivo e sem registro: não
    entregou (o Corrija-me só exporta as entregas)."""
    candidatos = (
        Aluno.objects.filter(turma__ano=ano, data_ingresso__lte=terca + SEMANA)
        .exclude(situacao=Aluno.Situacao.INVALIDO)
        .filter(Q(data_saida__isnull=True) | Q(data_saida__gte=terca))
        .exclude(pk__in=no_arquivo)
        .exclude(redacoes__tema_semana=terca)
    )
    novos = [
        ResultadoRedacao(aluno=aluno, tema_semana=terca, tema=tema.tema, entregue=False)
        for aluno in candidatos
    ]
    ResultadoRedacao.objects.bulk_create(novos)
    resumo.nao_entregues = len(novos)


def _pendencia(resumo, numero, motivo, ano, terca, matricula, linha, valores):
    registrar_pendencia(
        origem=Origem.REDACAO,
        motivo=motivo,
        ano=ano,
        data=terca,
        matricula=matricula,
        nome=linha.get("nome") or "",
        referencia=terca.isoformat(),
        dados={
            "tema_semana": terca.isoformat(),
            "valores": {
                c: (None if v is None else str(v)) if c != "entregue" else v
                for c, v in valores.items()
                if c != "tema"
            },
        },
    )
    resumo.pendencias.append((numero, PendenciaImportacao.Motivo(motivo).label))


@aplicador(Origem.REDACAO)
def aplicar_pendencia(pendencia, aluno, autor) -> str:
    """Associar é gravar a redação entregue para o aluno escolhido. Se ele ficou como não
    entregue nessa importação, o registro passa a entregue (com auditoria)."""
    terca = date.fromisoformat(pendencia.dados["tema_semana"])
    tema = TemaRedacao.objects.filter(data=terca).first()
    if tema is None:
        return "o tema da redação não está cadastrado"
    if not _no_aluno(aluno, terca):
        return "o tema é de antes do ingresso ou depois da saída do aluno"
    existente = ResultadoRedacao.objects.filter(aluno=aluno, tema_semana=terca).first()
    if existente is not None and existente.entregue:
        return "o aluno já tem redação entregue neste tema"
    brutos = pendencia.dados["valores"]
    valores = {
        "tema": tema.tema,
        "entregue": True,
        "banca": brutos.get("banca") or "",
        "nota_final": None if brutos.get("nota_final") is None else Decimal(brutos["nota_final"]),
        **{c: None if brutos.get(c) is None else Decimal(brutos[c]) for c in COMPETENCIAS_REDACAO},
    }
    _gravar(aluno, terca, valores, existente, autor)
    return ""
