"""Pendências de importação para associação manual (RN003, NF006, NF007, NF008, NF009, RN013).

Só dados sintéticos (NF017): matrículas `S26xxxx` e nomes inventados.
"""

from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from core.historico import ExclusaoProibidaError
from core.models import Aluno, PendenciaImportacao, RegistroAlteracao, Turma
from ingestao import pendencias as p
from ingestao.base import MOTIVO_RESTRICAO, ResumoImportacao

pytestmark = pytest.mark.django_db

Origem = PendenciaImportacao.Origem
Motivo = PendenciaImportacao.Motivo
Situacao = PendenciaImportacao.Situacao
DIA = date(2026, 3, 2)


@pytest.fixture
def aluno(turma_a):
    return Aluno.objects.create(
        matricula="S260001",
        nome="Aluno Sintético Um",
        data_ingresso=date(2026, 2, 2),
        turma=turma_a,
    )


@pytest.fixture
def aplicados(monkeypatch):
    """Aplicador falso da frequência: registra o que foi aplicado."""
    chamadas = []

    def aplicar(pendencia, aluno, autor):
        chamadas.append((pendencia.pk, aluno.pk))
        return ""

    monkeypatch.setitem(p.APLICADORES, Origem.FREQUENCIA, aplicar)
    return chamadas


def _pendencia(matricula="S269999", nome="Aluno Sintético Um", data=DIA, motivo=None):
    p.registrar_pendencia(
        origem=Origem.FREQUENCIA,
        motivo=motivo or Motivo.NAO_ENCONTRADA,
        ano=2026,
        data=data,
        matricula=matricula,
        nome=nome,
        referencia=data.isoformat(),
        dados={"data": data.isoformat()},
    )
    return PendenciaImportacao.objects.get(
        chave=p.chave_pendencia(Origem.FREQUENCIA, 2026, matricula, nome, data.isoformat())
    )


# --- Localizar o aluno (RN003) -----------------------------------------------------


def test_localizar_cada_motivo(aluno, turma_a):
    Aluno.objects.create(
        matricula="S260002",
        nome="Lançado Errado",
        data_ingresso=date(2026, 2, 2),
        turma=turma_a,
        situacao=Aluno.Situacao.INVALIDO,
    )
    loc = p.LocalizadorAlunos(["S260001", "S260002", "", "S269999"], 2026)
    assert loc.localizar("S260001") == (aluno, "")
    assert loc.localizar(" S260001 ") == (aluno, "")
    assert loc.localizar("") == (None, Motivo.EM_BRANCO)
    assert loc.localizar(None) == (None, Motivo.EM_BRANCO)
    assert loc.localizar("12345") == (None, Motivo.FORA_DO_PADRAO)
    assert loc.localizar("S250001") == (None, Motivo.OUTRO_ANO)
    assert loc.localizar("S269999") == (None, Motivo.NAO_ENCONTRADA)
    assert loc.localizar("S260002") == (None, Motivo.ALUNO_INVALIDO)


# --- Registro idempotente (NF008) ----------------------------------------------------


def test_registrar_e_idempotente():
    kw = {
        "origem": Origem.FREQUENCIA,
        "motivo": Motivo.EM_BRANCO,
        "ano": 2026,
        "data": DIA,
        "matricula": "",
        "nome": "Aluno Sintético",
        "referencia": DIA.isoformat(),
        "dados": {"v": 1},
    }
    assert p.registrar_pendencia(**kw) == p.NOVA
    assert p.registrar_pendencia(**kw) == p.PENDENTE
    # mesmo nome com outra caixa e acento é a mesma linha
    assert (
        p.registrar_pendencia(**{**kw, "nome": "ALUNO SINTETICO", "dados": {"v": 2}}) == p.PENDENTE
    )
    pendencia = PendenciaImportacao.objects.get()
    assert pendencia.dados == {"v": 2}
    assert (
        p.registrar_pendencia(**{**kw, "data": date(2026, 3, 3), "referencia": "2026-03-03"})
        == p.NOVA
    )


def test_pendencia_resolvida_nao_volta(diretor):
    pendencia = _pendencia()
    p.descartar([pendencia], autor=diretor)
    resultado = p.registrar_pendencia(
        origem=Origem.FREQUENCIA,
        motivo=Motivo.NAO_ENCONTRADA,
        ano=2026,
        data=DIA,
        matricula="S269999",
        nome="Aluno Sintético Um",
        referencia=DIA.isoformat(),
        dados={},
    )
    assert resultado == p.RESOLVIDA
    assert PendenciaImportacao.objects.count() == 1


# --- Associação e descarte (NF009) ---------------------------------------------------


def test_associar_em_grupo_audita_so_a_situacao(diretor, aluno, aplicados):
    uma, outra = _pendencia(data=DIA), _pendencia(data=date(2026, 3, 3))
    associadas, recusas = p.associar([uma, outra], aluno, autor=diretor)
    assert (associadas, recusas) == (2, [])
    assert {a for _, a in aplicados} == {"S260001"}
    uma.refresh_from_db()
    assert uma.situacao == Situacao.ASSOCIADA and uma.aluno == aluno
    assert uma.resolvida_por == diretor and uma.resolvida_em
    registros = RegistroAlteracao.objects.filter(modelo="core.pendenciaimportacao")
    assert {r.campo for r in registros} == {"situacao"} and registros.count() == 2
    texto = " ".join(f"{r.valor_anterior} {r.valor_novo}" for r in registros)
    assert "S26" not in texto and "Sintético" not in texto


def test_nome_diferente_exige_confirmacao(diretor, aluno, aplicados):
    pendencia = _pendencia(nome="Outra Pessoa Qualquer")
    with pytest.raises(p.AssociacaoRecusada, match="confirme"):
        p.associar([pendencia], aluno, autor=diretor)
    pendencia.refresh_from_db()
    assert pendencia.situacao == Situacao.PENDENTE and not aplicados
    assert p.associar([pendencia], aluno, autor=diretor, confirmar_nome=True) == (1, [])


def test_nome_em_branco_ou_so_com_acento_diferente_nao_pede_confirmacao(diretor, aluno, aplicados):
    vazio = _pendencia(nome="", data=DIA)
    acento = _pendencia(nome="aluno sintetico  um", data=date(2026, 3, 3))
    assert p.associar([vazio, acento], aluno, autor=diretor) == (2, [])


def test_aluno_de_outro_ano_ou_invalido_e_recusado(diretor, aluno, aplicados):
    turma_2025 = Turma.objects.create(nome="Turma A", ano=2025)
    antigo = Aluno.objects.create(
        matricula="S250001",
        nome="Aluno Sintético Um",
        data_ingresso=date(2025, 2, 3),
        turma=turma_2025,
    )
    pendencia = _pendencia()
    with pytest.raises(p.AssociacaoRecusada, match="ano letivo"):
        p.associar([pendencia], antigo, autor=diretor)
    aluno.situacao = Aluno.Situacao.INVALIDO
    aluno.save()
    with pytest.raises(p.AssociacaoRecusada, match="inválido"):
        p.associar([pendencia], aluno, autor=diretor)
    assert not aplicados


def test_recusa_do_aplicador_desfaz_o_que_ele_gravou(diretor, aluno, monkeypatch):
    def aplicar(pendencia, aluno, autor):
        Turma.objects.create(nome="Turma Fantasma", ano=2026)
        return "o aluno já tem registro neste dia"

    monkeypatch.setitem(p.APLICADORES, Origem.FREQUENCIA, aplicar)
    pendencia = _pendencia()
    associadas, recusas = p.associar([pendencia], aluno, autor=diretor)
    assert associadas == 0 and recusas == [(pendencia.pk, "o aluno já tem registro neste dia")]
    assert not Turma.objects.filter(nome="Turma Fantasma").exists()
    pendencia.refresh_from_db()
    assert pendencia.situacao == Situacao.PENDENTE


def test_restricao_do_banco_no_aplicador_isola_a_pendencia(diretor, aluno, monkeypatch):
    def aplicar(pendencia, aluno, autor):
        raise IntegrityError("simulada")

    monkeypatch.setitem(p.APLICADORES, Origem.FREQUENCIA, aplicar)
    pendencia = _pendencia()
    assert p.associar([pendencia], aluno, autor=diretor) == (0, [(pendencia.pk, MOTIVO_RESTRICAO)])


def test_origem_sem_aplicador_continua_pendente(diretor, aluno, monkeypatch):
    monkeypatch.delitem(p.APLICADORES, Origem.FREQUENCIA, raising=False)
    pendencia = _pendencia()
    assert p.associar([pendencia], aluno, autor=diretor) == (0, [(pendencia.pk, p.SEM_APLICADOR)])


def test_descartar_preserva_e_audita(diretor):
    pendencia = _pendencia()
    assert p.descartar([pendencia], autor=diretor) == 1
    assert p.descartar([pendencia], autor=diretor) == 0  # já resolvida
    pendencia.refresh_from_db()
    assert pendencia.situacao == Situacao.DESCARTADA and pendencia.aluno is None
    assert RegistroAlteracao.objects.filter(campo="situacao", valor_novo="DESCARTADA").count() == 1


# --- Modelo (NF007) ------------------------------------------------------------------


def test_sem_exclusao_fisica():
    pendencia = _pendencia()
    with pytest.raises(ExclusaoProibidaError):
        pendencia.delete()
    with pytest.raises(ExclusaoProibidaError):
        PendenciaImportacao.objects.all().delete()


def test_associada_exige_aluno_e_autor(diretor):
    pendencia = _pendencia()
    pendencia.situacao = Situacao.ASSOCIADA
    pendencia.resolvida_por = diretor
    with pytest.raises(IntegrityError), transaction.atomic():
        pendencia.save()


def test_resumo_conta_pendencias():
    resumo = ResumoImportacao(criados=1)
    resumo.pendencias.append((3, "Matrícula em branco"))
    assert resumo.total_linhas == 2
    assert resumo.assinatura()[-1] == 1


# --- Tela (RN013) --------------------------------------------------------------------

URL = reverse("web:pendencias")


def test_so_o_diretor_ve_pendencias(client, membro):
    _pendencia()
    resp = client.get(URL)
    assert resp.status_code == 302 and "/entrar/" in resp["Location"]
    client.force_login(membro)
    assert client.get(URL).status_code == 403
    assert client.post(URL, {"acao": "descartar"}).status_code == 403


def test_tela_lista_e_filtra(cliente_diretor):
    _pendencia()
    html = cliente_diretor.get(URL).content.decode()
    assert "S269999" in html and "Matrícula não encontrada" in html
    assert "S269999" not in cliente_diretor.get(URL + "?situacao=DESCARTADA").content.decode()
    assert "S269999" not in cliente_diretor.get(URL + "?origem=REDACAO").content.decode()
    assert "S269999" not in cliente_diretor.get(URL + "?ano=2025").content.decode()
    assert "S269999" in cliente_diretor.get(URL + "?ano=2026&situacao=todas").content.decode()


def test_decorador_registra_o_aplicador(monkeypatch):
    monkeypatch.setattr(p, "APLICADORES", {})

    @p.aplicador(Origem.REDACAO)
    def aplicar(pendencia, aluno, autor):
        return ""

    assert p.APLICADORES == {Origem.REDACAO: aplicar}


def test_tela_associa(cliente_diretor, aluno, aplicados):
    pendencia = _pendencia()
    resp = cliente_diretor.post(
        URL, {"acao": "associar", "pendencia": [pendencia.pk], "matricula": "S260001"}, follow=True
    )
    pendencia.refresh_from_db()
    assert pendencia.situacao == Situacao.ASSOCIADA
    mensagens = " ".join(str(m) for m in resp.context["messages"])
    assert "1 pendência(s) associada(s)" in mensagens
    assert "S26" not in mensagens and "Sintético" not in mensagens


def test_tela_pede_confirmacao_de_nome(cliente_diretor, aluno, aplicados):
    pendencia = _pendencia(nome="Outra Pessoa Qualquer")
    dados = {"acao": "associar", "pendencia": [pendencia.pk], "matricula": "S260001"}
    resp = cliente_diretor.post(URL, dados)
    assert resp.status_code == 200 and resp.context["confirmacao"]
    assert "Aluno Sintético Um" in resp.content.decode()  # nome do cadastro, só na página
    pendencia.refresh_from_db()
    assert pendencia.situacao == Situacao.PENDENTE
    cliente_diretor.post(URL, {**dados, "confirmar_nome": "1"})
    pendencia.refresh_from_db()
    assert pendencia.situacao == Situacao.ASSOCIADA


def test_tela_matricula_inexistente_e_sem_selecao(cliente_diretor):
    pendencia = _pendencia()
    resp = cliente_diretor.post(
        URL, {"acao": "associar", "pendencia": [pendencia.pk], "matricula": "S260077"}, follow=True
    )
    assert "Nenhum aluno do cadastro" in " ".join(str(m) for m in resp.context["messages"])
    resp = cliente_diretor.post(URL, {"acao": "descartar"}, follow=True)
    assert "Selecione ao menos uma" in " ".join(str(m) for m in resp.context["messages"])


def test_tela_associacao_recusada_mostra_motivo(cliente_diretor, aluno, aplicados):
    aluno.situacao = Aluno.Situacao.INVALIDO
    aluno.save()
    pendencia = _pendencia()
    resp = cliente_diretor.post(
        URL, {"acao": "associar", "pendencia": [pendencia.pk], "matricula": "S260001"}, follow=True
    )
    assert "Associação recusada" in " ".join(str(m) for m in resp.context["messages"])


def test_tela_mostra_recusa_do_aplicador(cliente_diretor, aluno, monkeypatch):
    monkeypatch.setitem(p.APLICADORES, Origem.FREQUENCIA, lambda *a: "já existe registro")
    pendencia = _pendencia()
    resp = cliente_diretor.post(
        URL, {"acao": "associar", "pendencia": [pendencia.pk], "matricula": "S260001"}, follow=True
    )
    assert "não foi associada: já existe registro" in " ".join(
        str(m) for m in resp.context["messages"]
    )


def test_tela_descarta(cliente_diretor):
    pendencia = _pendencia()
    cliente_diretor.post(URL, {"acao": "descartar", "pendencia": [pendencia.pk]})
    pendencia.refresh_from_db()
    assert pendencia.situacao == Situacao.DESCARTADA
