"""Importação do relatório de um simulado do P+ (RF004, RN003, RN004, RN006, RN009, RN010,
NF006, NF008, NF009).

O P+ exporta um arquivo por avaliação (`.xlsm` ou `.xlsx`, `ingestao.planilhas_casd`) e o
FAROL lê duas abas, unidas pelo `ID Aluno`:

- `Resultados e Classificações TRI`: a nota TRI por área (`<Área> - Etapa N - Nota`);
- `Acertos e Porcentagens TRI`: os acertos por área (`<Área> - Acertos`).

A associação é pela coluna `Matrícula`, que a equipe acrescenta ao relatório (RN003). O
arquivo não traz a data: o Diretor escolhe o ciclo do simulado (RN006) no formulário.

- Área com nota e acertos em branco: o aluno faltou àquela etapa (Etapa 1: LC e CH; Etapa 2:
  CN e MT) e a área fica `presente=False`, sem nota (RN009). Faltou às duas etapas: ausente.
  Só um dos dois em branco é inconsistente.
- Acertos de 0 a 45 por área; TRI de 0 a 1000, com uma casa decimal (RN010).
- Linha de outra avaliação (o `Nome Avaliação` difere do restante do arquivo), aluno
  repetido ou simulado de fora da janela do aluno (RN004) são inconsistentes.
- Matrícula sem aluno vira `PendenciaImportacao`; depois de associada, vale para o aluno
  escolhido nas reimportações.
- Reimportar atualiza o que mudou, com auditoria (NF009), e o resumo avisa quantos alunos já
  tinham resultado no ciclo (NF008).

As mensagens nunca trazem nome nem nota.
"""

import io
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from core.auditoria import registrar_alteracoes
from core.models import CicloCalendario, PendenciaImportacao, ResultadoSimulado
from ingestao import planilhas_casd
from ingestao.base import ResumoImportacao, linha_isolada, transacao_de_importacao
from ingestao.leitura import ArquivoInvalidoError, ler_bruto
from ingestao.pendencias import (
    RESOLVIDA,
    LocalizadorAlunos,
    aluno_da_linha,
    aplicador,
    registrar_pendencia,
)

Origem = PendenciaImportacao.Origem
Area = ResultadoSimulado.Area
SIGLAS = {
    Area.LINGUAGENS: "LC",
    Area.HUMANAS: "CH",
    Area.NATUREZA: "CN",
    Area.MATEMATICA: "MT",
}
MAX_ACERTOS = 45
MAX_TRI = Decimal("1000")
UMA_CASA = Decimal("0.1")
_MATRICULA = {"matricula", "rm"}


def _vazio(valor) -> bool:
    return valor is None or str(valor).strip() == ""


def _cabecalho(bruto, exigida: str) -> int:
    for indice, linha in enumerate(bruto[:10]):
        if exigida in {planilhas_casd.chave(c) for c in linha}:
            return indice
    raise ArquivoInvalidoError("Cabeçalho do relatório do P+ não encontrado (Nome Avaliação).")


def _coluna(chaves, *, comeca, termina=None, nome_legivel) -> int:
    for indice, c in enumerate(chaves):
        if c.startswith(comeca) and (termina is None or c.endswith(termina)):
            return indice
    raise ArquivoInvalidoError(f"Coluna obrigatória ausente no relatório do P+: {nome_legivel}.")


def ler_relatorio(arquivo, nome_arquivo) -> list[dict]:
    """Lê as duas abas do relatório e devolve uma linha por aluno, com as notas e os acertos
    de cada área (valores crus, validados na importação)."""
    if (nome_arquivo or "").lower().endswith(".csv"):
        raise ArquivoInvalidoError(
            "O relatório do P+ tem duas abas: envie o arquivo .xlsm ou .xlsx exportado."
        )
    conteudo = arquivo.read()
    notas = ler_bruto(io.BytesIO(conteudo), nome_arquivo, aba=planilhas_casd.ABA_NOTAS_PMAIS)
    acertos = ler_bruto(io.BytesIO(conteudo), nome_arquivo, aba=planilhas_casd.ABA_ACERTOS_PMAIS)
    i_notas = _cabecalho(notas, "nome avaliacao")
    i_acertos = _cabecalho(acertos, "nome avaliacao")
    cab_notas = [planilhas_casd.chave(c) for c in notas[i_notas]]
    cab_acertos = [planilhas_casd.chave(c) for c in acertos[i_acertos]]
    try:
        col_matricula = next(i for i, c in enumerate(cab_notas) if c in _MATRICULA)
    except StopIteration:
        raise ArquivoInvalidoError(
            "A aba de resultados precisa da coluna Matrícula (acrescente-a ao relatório, RN003)."
        ) from None
    ident = {
        "avaliacao": ("nome avaliacao", "Nome Avaliação"),
        "id": ("id aluno", "ID Aluno"),
        "nome": ("nome aluno", "Nome Aluno"),
    }
    col_n = {k: _coluna(cab_notas, comeca=v[0], nome_legivel=v[1]) for k, v in ident.items()}
    id_acertos = _coluna(cab_acertos, comeca="id aluno", nome_legivel="ID Aluno")
    col_tri, col_acertos = {}, {}
    for area, (nome, etapa) in planilhas_casd.AREAS_PMAIS.items():
        base = planilhas_casd.chave(nome)
        col_tri[area] = _coluna(
            cab_notas, comeca=base, termina="nota", nome_legivel=f"{nome} - Etapa {etapa} - Nota"
        )
        col_acertos[area] = _coluna(
            cab_acertos, comeca=base, termina="acertos", nome_legivel=f"{nome} - Acertos"
        )

    def valor(linha, i):
        return linha[i] if i < len(linha) else None

    por_id = {}
    for linha in acertos[i_acertos + 1 :]:
        identificador = _texto(valor(linha, id_acertos))
        if identificador:
            por_id[identificador] = linha
    linhas = []
    for numero, linha in enumerate(notas[i_notas + 1 :], start=i_notas + 2):
        if all(_vazio(v) for v in linha):
            continue
        identificador = _texto(valor(linha, col_n["id"]))
        outra = por_id.get(identificador)
        linhas.append(
            {
                "_linha": numero,
                "matricula": _texto(valor(linha, col_matricula)),
                "nome": str(valor(linha, col_n["nome"]) or "").strip(),
                "avaliacao": planilhas_casd.chave(valor(linha, col_n["avaliacao"])),
                "tem_acertos": outra is not None,
                "areas": {
                    area: (
                        valor(linha, col_tri[area]),
                        valor(outra, col_acertos[area]) if outra else None,
                    )
                    for area in planilhas_casd.AREAS_PMAIS
                },
            }
        )
    if not linhas:
        raise ArquivoInvalidoError("O relatório do P+ não tem linhas de aluno.")
    return linhas


def _texto(valor) -> str:
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor if valor is not None else "").strip()


def exemplo(ano: int) -> bytes:
    """Modelo para download: o relatório no layout real, com dois alunos sintéticos (NF017):
    um presente nas duas etapas e outro que faltou à Etapa 1."""
    aa = ano % 100
    todas = {a: 650.0 for a in planilhas_casd.AREAS_PMAIS}
    acertos = {a: 30 for a in planilhas_casd.AREAS_PMAIS}
    so_etapa_2 = {a: (v if a in ("NATUREZA", "MATEMATICA") else None) for a, v in todas.items()}
    acertos_2 = {a: (v if a in ("NATUREZA", "MATEMATICA") else None) for a, v in acertos.items()}
    alunos = [
        {"matricula": f"S{aa}0001", "nome": "Aluno Exemplo Um", "id_aluno": 1001,
         "inscricao": "0001001", "turma": "Turma 1", "notas": todas, "acertos": acertos},
        {"matricula": f"S{aa}0002", "nome": "Aluno Exemplo Dois", "id_aluno": 1002,
         "inscricao": "0001002", "turma": "Turma 2", "notas": so_etapa_2, "acertos": acertos_2},
    ]  # fmt: skip
    return planilhas_casd.relatorio_pmais("Simulado de exemplo", ano, alunos)


@dataclass
class ResumoSimulados(ResumoImportacao):
    """Conta linhas (aluno): criada, atualizada ou sem alteração."""

    ausentes: int = 0
    ausencias_parciais: int = 0

    def assinatura(self) -> list[int]:
        return super().assinatura() + [self.ausentes, self.ausencias_parciais]


def _inteiro(valor) -> int | None:
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor
    texto = str(valor).strip()
    return int(texto) if texto.isdigit() else None


def _tri(valor) -> Decimal | None:
    try:
        nota = Decimal(str(valor).strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not nota.is_finite():
        return None
    return nota.quantize(UMA_CASA)


def _validar(linha) -> tuple[dict | None, str]:
    """Devolve `{area: (presente, acertos, tri)}` ou o motivo da recusa."""
    if not linha["tem_acertos"]:
        return None, "aluno sem linha na aba de acertos (ID Aluno)"
    areas = {}
    for area, (tri, acertos) in linha["areas"].items():
        sigla = SIGLAS[area]
        if _vazio(tri) and _vazio(acertos):
            areas[area] = (False, None, None)  # faltou à etapa (RN009)
            continue
        if _vazio(tri) or _vazio(acertos):
            return None, f"nota e acertos de {sigla} não batem (um deles em branco)"
        n_acertos, n_tri = _inteiro(acertos), _tri(tri)
        if n_acertos is None or not 0 <= n_acertos <= MAX_ACERTOS:
            return None, f"acertos de {sigla} fora de 0 a {MAX_ACERTOS}"
        if n_tri is None or not 0 <= n_tri <= MAX_TRI:
            return None, f"nota TRI de {sigla} fora de 0 a 1000"
        areas[area] = (True, n_acertos, n_tri)
    return areas, ""


def _dia_do_simulado(ciclo) -> date:
    return ciclo.data_simulado or ciclo.data_fim


def _no_aluno(aluno, dia) -> bool:
    return aluno.data_ingresso <= dia and (aluno.data_saida is None or dia <= aluno.data_saida)


def _gravar(aluno, ciclo, areas, existentes, autor) -> str:
    """Cria ou atualiza as quatro áreas. Devolve "criado", "atualizado" ou "igual"."""
    havia = any((aluno.pk, ciclo.pk, area) in existentes for area in Area.values)
    mudou = False
    for area in Area.values:
        presente, acertos, tri = areas[area]
        valores = {"presente": presente, "acertos": acertos, "nota_tri": tri}
        resultado = existentes.get((aluno.pk, ciclo.pk, area))
        if resultado is None:
            ResultadoSimulado.objects.create(aluno=aluno, ciclo=ciclo, area=area, **valores)
            mudou = True
            continue
        anteriores = {c: getattr(resultado, c) for c in valores}
        if all(anteriores[c] == v for c, v in valores.items()):
            continue
        for campo, novo in valores.items():
            setattr(resultado, campo, novo)
        resultado.save(update_fields=list(valores))
        registrar_alteracoes(autor=autor, objeto=resultado, anteriores=anteriores)
        mudou = True
    if not havia:
        return "criado"
    return "atualizado" if mudou else "igual"


def importar_simulados(linhas, *, ano: int, ciclo: CicloCalendario, autor, gravar: bool):
    resumo = ResumoSimulados()
    with transacao_de_importacao(gravar):
        principal = Counter(linha["avaliacao"] for linha in linhas).most_common(1)[0][0]
        localizador = LocalizadorAlunos([linha["matricula"] for linha in linhas], ano)
        validas, vistos = [], set()
        for linha in linhas:
            numero, matricula = linha["_linha"], linha["matricula"]

            def recusar(motivo, numero=numero, matricula=matricula):
                resumo.inconsistentes.append((numero, matricula[:30], motivo))

            if linha["avaliacao"] != principal:
                recusar("avaliação diferente do restante do arquivo")
                continue
            areas, motivo = _validar(linha)
            if areas is None:
                recusar(motivo)
                continue
            aluno, motivo = aluno_da_linha(
                localizador,
                origem=Origem.SIMULADO,
                ano=ano,
                matricula=matricula,
                nome=linha["nome"],
                referencia=ciclo.pk,
            )
            if aluno is None and motivo == RESOLVIDA:
                resumo.sem_alteracao += 1  # pendência descartada pelo Diretor
                continue
            if aluno is None:
                _pendencia(resumo, numero, motivo, ano, ciclo, matricula, linha["nome"], areas)
                continue
            if aluno.pk in vistos:
                recusar("aluno repetido no relatório")
                continue
            vistos.add(aluno.pk)
            if not _no_aluno(aluno, _dia_do_simulado(ciclo)):
                recusar("simulado antes do ingresso ou depois da saída do aluno (RN004)")
                continue
            validas.append((numero, aluno, areas))

        existentes = {
            (r.aluno_id, r.ciclo_id, r.area): r
            for r in ResultadoSimulado.objects.filter(
                aluno_id__in={a.pk for _, a, _ in validas}, ciclo=ciclo
            )
        }
        for numero, aluno, areas in validas:

            def recusar(motivo, numero=numero, matricula=aluno.pk):
                resumo.inconsistentes.append((numero, matricula, motivo))

            with linha_isolada(recusar):
                situacao = _gravar(aluno, ciclo, areas, existentes, autor)
                if situacao == "criado":
                    resumo.criados += 1
                elif situacao == "atualizado":
                    resumo.atualizados += 1
                else:
                    resumo.sem_alteracao += 1
                presencas = [p for p, _, _ in areas.values()]
                if not any(presencas):
                    resumo.ausentes += 1
                elif not all(presencas):
                    resumo.ausencias_parciais += 1
        ja_existiam = len({a for a, _, _ in existentes})
        if ja_existiam:
            resumo.sobreposicoes.append(
                f"{ja_existiam} aluno(s) já têm resultado neste ciclo; confirmar atualiza "
                f"{resumo.atualizados} deles"
            )
    return resumo


def _dados(ciclo, areas) -> dict:
    return {
        "ciclo": ciclo.pk,
        "areas": {area: [p, a, None if t is None else str(t)] for area, (p, a, t) in areas.items()},
    }


def _pendencia(resumo, numero, motivo, ano, ciclo, matricula, nome, areas):
    registrar_pendencia(
        origem=Origem.SIMULADO,
        motivo=motivo,
        ano=ano,
        data=_dia_do_simulado(ciclo),
        matricula=matricula,
        nome=nome,
        referencia=ciclo.pk,
        dados=_dados(ciclo, areas),
    )
    resumo.pendencias.append((numero, PendenciaImportacao.Motivo(motivo).label))


@aplicador(Origem.SIMULADO)
def aplicar_pendencia(pendencia, aluno, autor) -> str:
    """Associar é gravar as quatro áreas do simulado para o aluno escolhido."""
    ciclo = CicloCalendario.objects.filter(pk=pendencia.dados["ciclo"]).first()
    if ciclo is None:
        return "o ciclo do simulado não existe mais"
    if not _no_aluno(aluno, _dia_do_simulado(ciclo)):
        return "o simulado é de antes do ingresso ou depois da saída do aluno"
    if ResultadoSimulado.objects.filter(aluno=aluno, ciclo=ciclo).exists():
        return "o aluno já tem resultado neste simulado"
    areas = {
        area: (p, a, None if t is None else Decimal(t))
        for area, (p, a, t) in pendencia.dados["areas"].items()
    }
    _gravar(aluno, ciclo, areas, {}, autor)
    return ""
