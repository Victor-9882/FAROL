"""Importação do calendário letivo, dos ciclos e dos temas de redação (RF007).

Regras:
- Chaves: `data` (dia, tema), `inicio` (período) e `data_inicio` (ciclo). Reimportar atualiza o
  que mudou e
  audita cada campo (NF009); o que não mudou conta como sem alteração (NF008).
- Registro ausente do arquivo não é tocado (NF007).
- Linha com data de outro ano letivo é inconsistente (protege contra arquivo errado).
- Ciclo com duração diferente de 14 dias é só aviso: o calendário manda (RN006).
Sem dado pessoal; as mensagens citam só a linha e o motivo.
"""

import unicodedata
from dataclasses import dataclass, field
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import transaction

from core.auditoria import registrar_alteracoes
from core.calendario import aviso_duracao
from core.models import (
    CicloCalendario,
    DiaCalendario,
    PeriodoLetivo,
    RegistroImportacao,
    TemaRedacao,
)
from ingestao.leitura import ler_data

_SIM = {"s", "sim", "1", "true", "verdadeiro", "v"}
_NAO = {"n", "nao", "0", "false", "falso", "f"}


@dataclass
class ResumoCalendario:
    criados: int = 0
    atualizados: int = 0
    sem_alteracao: int = 0
    inconsistentes: list[tuple[int, str]] = field(default_factory=list)
    avisos: list[tuple[int, str]] = field(default_factory=list)


def _vazio(valor) -> bool:
    return valor is None or str(valor).strip() == ""


def _booleano(valor) -> bool | None:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = unicodedata.normalize("NFKD", str(valor).strip().lower())
    texto = texto.encode("ascii", "ignore").decode()
    if texto in _SIM:
        return True
    return False if texto in _NAO else None


def _data_obrigatoria(linha, campo, ano=None):
    bruta = linha.get(campo)
    if _vazio(bruta):
        return None, f"{campo.replace('_', ' ')} em branco"
    data = ler_data(bruta)
    if data is None:
        return None, f"{campo.replace('_', ' ')} inválida (use dd/mm/aaaa ou aaaa-mm-dd)"
    if ano is not None and data.year != ano:
        return None, "data de outro ano letivo"
    return data, ""


def _texto(linha, campo, maximo, obrigatorio):
    valor = " ".join(str(linha.get(campo) or "").split())
    if obrigatorio and not valor:
        return None, f"{campo} em branco"
    if len(valor) > maximo:
        return None, f"{campo} com mais de {maximo} caracteres"
    return valor, ""


def _validar_dia(linha, ano):
    data, motivo = _data_obrigatoria(linha, "data", ano)
    if motivo:
        return None, motivo
    bruto = linha.get("dia_letivo")
    letivo = None if _vazio(bruto) else _booleano(bruto)
    if letivo is None:
        return None, "dia letivo inválido (use S/N, sim/não ou 1/0)"
    descricao, motivo = _texto(linha, "descricao", 100, False)
    if motivo:
        return None, motivo
    return {"data": data, "letivo": letivo, "descricao": descricao}, ""


def _validar_periodo(linha, ano):
    inicio, motivo = _data_obrigatoria(linha, "inicio", ano)
    if motivo:
        return None, motivo
    fim, motivo = _data_obrigatoria(linha, "fim")
    if motivo:
        return None, motivo
    descricao, motivo = _texto(linha, "descricao", 100, False)
    if motivo:
        return None, motivo
    return {"inicio": inicio, "fim": fim, "descricao": descricao}, ""


def _validar_ciclo(linha, ano):
    inicio, motivo = _data_obrigatoria(linha, "data_inicio", ano)
    if motivo:
        return None, motivo
    fim, motivo = _data_obrigatoria(linha, "data_fim")
    if motivo:
        return None, motivo
    simulado = None
    if not _vazio(linha.get("data_simulado")):
        simulado, motivo = _data_obrigatoria(linha, "data_simulado")
        if motivo:
            return None, motivo
    return {"data_inicio": inicio, "data_fim": fim, "data_simulado": simulado}, ""


def _validar_tema(linha, ano):
    data, motivo = _data_obrigatoria(linha, "data", ano)
    if motivo:
        return None, motivo
    tema, motivo = _texto(linha, "tema", 200, True)
    if motivo:
        return None, motivo
    return {"data": data, "tema": tema}, ""


def _importar(modelo, chave, validar, linhas, *, ano, autor, gravar, avisar=None):
    resumo = ResumoCalendario()
    with transaction.atomic():
        validas, vistas = [], set()
        for linha in linhas:
            numero = linha["_linha"]
            dados, motivo = validar(linha, ano)
            if dados is None:
                resumo.inconsistentes.append((numero, motivo))
            elif dados[chave] in vistas:
                resumo.inconsistentes.append((numero, "data repetida no arquivo"))
            else:
                vistas.add(dados[chave])
                validas.append((numero, dados))
        existentes = modelo.objects.in_bulk(list(vistas), field_name=chave)
        for numero, dados in validas:
            objeto = existentes.get(dados[chave])
            if objeto is None:
                objeto = modelo(**dados)
            else:
                anteriores = {c: getattr(objeto, c) for c in dados}
                if all(anteriores[c] == v for c, v in dados.items()):
                    resumo.sem_alteracao += 1
                    continue
                for campo, valor in dados.items():
                    setattr(objeto, campo, valor)
            novo = objeto.pk is None
            try:
                objeto.full_clean()
            except ValidationError as erro:
                resumo.inconsistentes.append((numero, "; ".join(erro.messages)))
                continue
            objeto.save()
            if novo:
                resumo.criados += 1
            else:
                registrar_alteracoes(autor=autor, objeto=objeto, anteriores=anteriores)
                resumo.atualizados += 1
            if avisar and (aviso := avisar(objeto)):
                resumo.avisos.append((numero, aviso))
        if not gravar:
            transaction.set_rollback(True)
    return resumo


def importar_periodos(linhas, *, ano, autor, gravar):
    return _importar(
        PeriodoLetivo, "inicio", _validar_periodo, linhas, ano=ano, autor=autor, gravar=gravar
    )


def importar_dias(linhas, *, ano, autor, gravar):
    return _importar(
        DiaCalendario, "data", _validar_dia, linhas, ano=ano, autor=autor, gravar=gravar
    )


def importar_ciclos(linhas, *, ano, autor, gravar):
    return _importar(
        CicloCalendario,
        "data_inicio",
        _validar_ciclo,
        linhas,
        ano=ano,
        autor=autor,
        gravar=gravar,
        avisar=lambda c: aviso_duracao(c.data_inicio, c.data_fim),
    )


def importar_temas(linhas, *, ano, autor, gravar):
    return _importar(
        TemaRedacao, "data", _validar_tema, linhas, ano=ano, autor=autor, gravar=gravar
    )


TIPOS = {
    "periodos": SimpleNamespace(
        rotulo="Períodos letivos",
        registro=RegistroImportacao.Tipo.PERIODOS,
        modelo=PeriodoLetivo,
        colunas={"inicio": ("data_inicio",), "fim": ("data_fim",), "descricao": ()},
        opcionais=frozenset({"descricao"}),
        exemplos=[
            {"inicio": "02/02/2026", "fim": "03/07/2026", "descricao": "Primeiro período"},
            {"inicio": "20/07/2026", "fim": "11/12/2026", "descricao": "Segundo período"},
        ],
        importar=importar_periodos,
    ),
    "dias": SimpleNamespace(
        rotulo="Dias não letivos e exceções",
        registro=RegistroImportacao.Tipo.CALENDARIO,
        modelo=DiaCalendario,
        colunas={"data": (), "dia_letivo": ("dia", "letivo"), "descricao": ("motivo",)},
        opcionais=frozenset({"descricao"}),
        exemplos=[
            {"data": "02/02/2026", "dia_letivo": "S", "descricao": ""},
            {"data": "16/02/2026", "dia_letivo": "N", "descricao": "Carnaval"},
        ],
        importar=importar_dias,
    ),
    "ciclos": SimpleNamespace(
        rotulo="Ciclos",
        registro=RegistroImportacao.Tipo.CICLOS,
        modelo=CicloCalendario,
        colunas={"data_inicio": (), "data_fim": (), "data_simulado": ()},
        opcionais=frozenset({"data_simulado"}),
        exemplos=[
            {"data_inicio": "02/02/2026", "data_fim": "15/02/2026", "data_simulado": "15/02/2026"},
            {"data_inicio": "16/02/2026", "data_fim": "01/03/2026", "data_simulado": "01/03/2026"},
        ],
        importar=importar_ciclos,
    ),
    "temas": SimpleNamespace(
        rotulo="Temas de redação",
        registro=RegistroImportacao.Tipo.TEMAS,
        modelo=TemaRedacao,
        colunas={"data": ("terca",), "tema": ()},
        opcionais=frozenset(),
        exemplos=[
            {"data": "03/02/2026", "tema": "Tema de exemplo um"},
            {"data": "10/02/2026", "tema": "Tema de exemplo dois"},
        ],
        importar=importar_temas,
    ),
}
