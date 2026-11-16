"""Importação dos resultados de simulados do P+ (RF004, RN003, RN004, RN009, RN010, NF006, NF008).

O arquivo tem uma linha por aluno e simulado: `data` do simulado, `matricula`, `nome`
(opcional), `presenca` (`Presente`/`Ausente`) e, por área do ENEM, os acertos brutos e a
nota TRI: `lc_acertos`, `lc_tri`, `ch_…`, `cn_…`, `mt_…` (RN010). O nome do simulado é
opcional e não é guardado.

- O simulado pertence ao ciclo do calendário que tem essa `data_simulado` ou, se nenhum tem,
  ao ciclo que contém a data (RN006). Sem ciclo, a linha é inconsistente.
- Ausente (RN009): grava as quatro áreas com `presente=False` e sem nota. Ausente com nota
  ou presente sem nota é inconsistente.
- Acertos de 0 a 45 por área; TRI de 0 a 1000, com uma casa decimal (vírgula ou ponto).
- Simulado antes do ingresso (RN004) ou depois da saída do aluno é inconsistente.
- Matrícula sem aluno vira `PendenciaImportacao` (RN003).
- Reimportar atualiza o que mudou, com auditoria (NF009), e o resumo avisa quantos
  resultados já existiam (NF008).

As mensagens nunca trazem nome nem nota.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from core.auditoria import registrar_alteracoes
from core.models import CicloCalendario, PendenciaImportacao, ResultadoSimulado
from ingestao.base import ResumoImportacao, linha_isolada, transacao_de_importacao
from ingestao.cadastro import _chave_nome
from ingestao.calendario import _booleano, _vazio
from ingestao.leitura import ler_data
from ingestao.pendencias import RESOLVIDA, LocalizadorAlunos, aplicador, registrar_pendencia

Origem = PendenciaImportacao.Origem
Area = ResultadoSimulado.Area

AREAS = {
    "lc": Area.LINGUAGENS,
    "ch": Area.HUMANAS,
    "cn": Area.NATUREZA,
    "mt": Area.MATEMATICA,
}
MAX_ACERTOS = 45
MAX_TRI = Decimal("1000")
UMA_CASA = Decimal("0.1")

COLUNAS = {
    "data": ("data_simulado", "data_da_prova"),
    "matricula": ("rm", "matricula_aluno"),
    "nome": ("aluno", "nome_completo"),
    "presenca": ("presente", "situacao", "status"),
    "simulado": ("prova", "nome_simulado"),
    **{f"{sigla}_{tipo}": () for sigla in AREAS for tipo in ("acertos", "tri")},
}
OPCIONAIS = frozenset({"nome", "simulado"})
_PRESENTE = {"presente", "p"}
_AUSENTE = {"ausente", "a", "faltou"}


def exemplos(ano: int) -> list[dict]:
    """Linhas sintéticas do modelo para download, no ano letivo pedido (NF017)."""
    aa = ano % 100
    presente = {f"{s}_acertos": 30 for s in AREAS} | {f"{s}_tri": "650,0" for s in AREAS}
    ausente = {f"{s}_{t}": "" for s in AREAS for t in ("acertos", "tri")}
    base = {"data": f"15/03/{ano}", "simulado": f"Simulado de exemplo {ano}"}
    return [
        base
        | {"matricula": f"S{aa}0001", "nome": "Aluno Exemplo Um", "presenca": "Presente"}
        | presente,
        base
        | {"matricula": f"S{aa}0002", "nome": "Aluno Exemplo Dois", "presenca": "Ausente"}
        | ausente,
    ]


@dataclass
class ResumoSimulados(ResumoImportacao):
    """Conta linhas (aluno e simulado): criada, atualizada ou sem alteração."""

    ausentes: int = 0
    ciclos: int = 0

    def assinatura(self) -> list[int]:
        return super().assinatura() + [self.ausentes]


def _presenca(valor) -> bool | None:
    texto = str(valor or "").strip().lower()
    if texto in _PRESENTE:
        return True
    if texto in _AUSENTE:
        return False
    return _booleano(valor) if texto else None


def _inteiro(valor) -> int | None:
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, int):
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


def _validar(linha, ano) -> tuple[dict | None, str]:
    bruta = linha.get("data")
    if _vazio(bruta):
        return None, "data do simulado em branco"
    data = ler_data(bruta)
    if data is None:
        return None, "data do simulado inválida (use dd/mm/aaaa ou aaaa-mm-dd)"
    if data.year != ano:
        return None, "data do simulado fora do ano letivo informado"
    presente = _presenca(linha.get("presenca"))
    if presente is None:
        return None, "presença inválida (use Presente ou Ausente)"
    notas = {}
    for sigla, area in AREAS.items():
        acertos, tri = linha.get(f"{sigla}_acertos"), linha.get(f"{sigla}_tri")
        if not presente:
            if not (_vazio(acertos) and _vazio(tri)):
                return None, "aluno ausente com nota (RN009)"
            continue
        if _vazio(acertos) or _vazio(tri):
            return None, f"nota de {sigla.upper()} em branco para aluno presente"
        n_acertos, n_tri = _inteiro(acertos), _tri(tri)
        if n_acertos is None or not 0 <= n_acertos <= MAX_ACERTOS:
            return None, f"acertos de {sigla.upper()} fora de 0 a {MAX_ACERTOS}"
        if n_tri is None or not 0 <= n_tri <= MAX_TRI:
            return None, f"nota TRI de {sigla.upper()} fora de 0 a 1000"
        notas[area] = (n_acertos, n_tri)
    return {"data": data, "presente": presente, "notas": notas}, ""


def _ciclo_de(data, ciclos) -> CicloCalendario | None:
    """O ciclo cuja data do simulado é `data` ou, na falta dele, o que contém `data`."""
    for ciclo in ciclos:
        if ciclo.data_simulado == data:
            return ciclo
    for ciclo in ciclos:
        if ciclo.data_inicio <= data <= ciclo.data_fim:
            return ciclo
    return None


def _no_aluno(aluno, dia) -> bool:
    return aluno.data_ingresso <= dia and (aluno.data_saida is None or dia <= aluno.data_saida)


def _valores(presente, notas, area) -> dict:
    acertos, tri = notas.get(area, (None, None))
    return {"presente": presente, "acertos": acertos, "nota_tri": tri}


def _gravar(aluno, ciclo, presente, notas, existentes, autor) -> str:
    """Cria ou atualiza as quatro áreas. Devolve "criado", "atualizado" ou "igual"."""
    havia = any((aluno.pk, ciclo.pk, area) in existentes for area in Area.values)
    mudou = False
    for area in Area.values:
        valores = _valores(presente, notas, area)
        resultado = existentes.get((aluno.pk, ciclo.pk, area))
        if resultado is None:
            ResultadoSimulado.objects.create(aluno=aluno, ciclo=ciclo, area=area, **valores)
            mudou = True
            continue
        anteriores = {c: getattr(resultado, c) for c in valores}
        if all(anteriores[c] == v for c, v in valores.items()):
            continue
        for campo, valor in valores.items():
            setattr(resultado, campo, valor)
        resultado.save(update_fields=list(valores))
        registrar_alteracoes(autor=autor, objeto=resultado, anteriores=anteriores)
        mudou = True
    if not havia:
        return "criado"
    return "atualizado" if mudou else "igual"


def importar_simulados(linhas, *, ano: int, autor, gravar: bool):
    resumo = ResumoSimulados()
    with transacao_de_importacao(gravar):
        ciclos = list(CicloCalendario.objects.filter(data_inicio__year=ano))
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
            ciclo = _ciclo_de(dados["data"], ciclos)
            if ciclo is None:
                recusar("nenhum ciclo do calendário contém a data do simulado (RN006)")
                continue
            aluno, motivo = localizador.localizar(matricula)
            chave = (
                (aluno.pk, ciclo.pk)
                if aluno
                else (matricula, _chave_nome(linha.get("nome")), ciclo.pk)
            )
            if chave in vistas:
                recusar("aluno repetido no mesmo simulado")
                continue
            vistas.add(chave)
            if aluno is None:
                _pendencia(resumo, numero, motivo, ano, ciclo, matricula, linha, dados)
                continue
            if not _no_aluno(aluno, dados["data"]):
                recusar("simulado antes do ingresso ou depois da saída do aluno (RN004)")
                continue
            validas.append((numero, aluno, ciclo, dados))

        alunos = {aluno.pk for _, aluno, _, _ in validas}
        existentes = {
            (r.aluno_id, r.ciclo_id, r.area): r
            for r in ResultadoSimulado.objects.filter(
                aluno_id__in=alunos, ciclo__in={c for _, _, c, _ in validas}
            )
        }
        for numero, aluno, ciclo, dados in validas:

            def recusar(motivo, numero=numero, matricula=aluno.pk):
                resumo.inconsistentes.append((numero, matricula, motivo))

            with linha_isolada(recusar):
                situacao = _gravar(
                    aluno, ciclo, dados["presente"], dados["notas"], existentes, autor
                )
                if situacao == "criado":
                    resumo.criados += 1
                elif situacao == "atualizado":
                    resumo.atualizados += 1
                else:
                    resumo.sem_alteracao += 1
                if not dados["presente"]:
                    resumo.ausentes += 1
        resumo.ciclos = len({c.pk for _, _, c, _ in validas})
        ja_existiam = len({(a, c) for a, c, _ in existentes})
        if ja_existiam:
            resumo.sobreposicoes.append(
                f"{ja_existiam} aluno(s) já têm resultado nos simulados deste arquivo; "
                f"confirmar atualiza {resumo.atualizados} deles"
            )
    return resumo


def _pendencia(resumo, numero, motivo, ano, ciclo, matricula, linha, dados):
    notas = {area: [a, str(t)] for area, (a, t) in dados["notas"].items()}
    situacao = registrar_pendencia(
        origem=Origem.SIMULADO,
        motivo=motivo,
        ano=ano,
        data=dados["data"],
        matricula=matricula,
        nome=linha.get("nome") or "",
        referencia=ciclo.pk,
        dados={"ciclo": ciclo.pk, "presente": dados["presente"], "notas": notas},
    )
    if situacao == RESOLVIDA:
        resumo.sem_alteracao += 1  # já associada ou descartada: nada a fazer
    else:
        resumo.pendencias.append((numero, PendenciaImportacao.Motivo(motivo).label))


@aplicador(Origem.SIMULADO)
def aplicar_pendencia(pendencia, aluno, autor) -> str:
    """Associar é gravar as quatro áreas do simulado para o aluno escolhido."""
    ciclo = CicloCalendario.objects.filter(pk=pendencia.dados["ciclo"]).first()
    if ciclo is None:
        return "o ciclo do simulado não existe mais"
    if not _no_aluno(aluno, pendencia.data):
        return "o simulado é de antes do ingresso ou depois da saída do aluno"
    if ResultadoSimulado.objects.filter(aluno=aluno, ciclo=ciclo).exists():
        return "o aluno já tem resultado neste simulado"
    notas = {area: (a, Decimal(t)) for area, (a, t) in pendencia.dados["notas"].items()}
    _gravar(aluno, ciclo, pendencia.dados["presente"], notas, {}, autor)
    return ""
