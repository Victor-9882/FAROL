"""Testes do modelo de dados inicial (#6): RN003, RN011, NF007, NF008.

Só dados sintéticos (NF017): nomes e matrículas abaixo são inventados.
"""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, transaction

from core.historico import ExclusaoProibidaError
from core.models import (
    Alerta,
    Aluno,
    CicloCalendario,
    HistoricoTurma,
    Intervencao,
    RegistroFrequencia,
    ResultadoRedacao,
    ResultadoSimulado,
    Turma,
    Usuario,
)
from inteligencia.models import RegraAlerta

pytestmark = pytest.mark.django_db

SP = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def turma_a():
    return Turma.objects.create(nome="Turma A", ano=2026)


@pytest.fixture
def turma_b():
    return Turma.objects.create(nome="Turma B", ano=2026)


@pytest.fixture
def aluno(turma_a):
    return Aluno.objects.create(
        matricula="S260001",
        nome="Aluno Sintético Um",
        data_ingresso=date(2026, 2, 9),
        turma=turma_a,
    )


@pytest.fixture
def ciclo():
    return CicloCalendario.objects.create(data_inicio=date(2026, 3, 2), data_fim=date(2026, 3, 16))


@pytest.fixture
def diretor():
    return Usuario.objects.create_user(
        "diretor", "diretor@exemplo.org", "x", perfil=Usuario.Perfil.DIRETOR
    )


def falha_no_banco(criar):
    """Executa `criar` e confirma que o banco recusou a gravação."""
    with pytest.raises(IntegrityError), transaction.atomic():
        criar()


# --- RN003: matrícula como identificador único -------------------------------------


def test_matricula_e_a_chave_do_aluno(aluno):
    assert Aluno._meta.pk.name == "matricula"
    assert Aluno.objects.get(pk="S260001") == aluno


def test_matricula_repetida_e_recusada(aluno, turma_b):
    falha_no_banco(
        lambda: Aluno.objects.create(
            matricula="S260001",
            nome="Outro Nome Sintético",
            data_ingresso=date(2026, 4, 1),
            turma=turma_b,
        )
    )


def test_matricula_em_branco_e_recusada(turma_a):
    # A revisão estática achou matrículas em branco no export do Corrija-me.
    falha_no_banco(
        lambda: Aluno.objects.create(
            matricula="", nome="Sem Matrícula", data_ingresso=date(2026, 2, 9), turma=turma_a
        )
    )


# --- RN011: mudança de turma preserva o histórico ----------------------------------


def test_aluno_novo_abre_historico_na_turma_de_ingresso(aluno, turma_a):
    periodo = aluno.historico_turmas.get()
    assert periodo.turma == turma_a
    assert periodo.data_inicio == date(2026, 2, 9)
    assert periodo.data_fim is None


def test_mudar_de_turma_preserva_o_historico(aluno, turma_a, turma_b):
    aluno.mudar_turma(turma_b, date(2026, 5, 4))

    aluno.refresh_from_db()
    assert aluno.turma == turma_b
    periodos = list(aluno.historico_turmas.values_list("turma__nome", "data_inicio", "data_fim"))
    assert periodos == [
        ("Turma A", date(2026, 2, 9), date(2026, 5, 4)),
        ("Turma B", date(2026, 5, 4), None),
    ]


def test_turma_em_uma_data_considera_o_historico(aluno, turma_a, turma_b):
    aluno.mudar_turma(turma_b, date(2026, 5, 4))

    assert aluno.turma_em(date(2026, 2, 8)) is None  # antes do ingresso (RN004)
    assert aluno.turma_em(date(2026, 2, 9)) == turma_a
    assert aluno.turma_em(date(2026, 5, 3)) == turma_a
    assert aluno.turma_em(date(2026, 5, 4)) == turma_b


def test_registros_anteriores_continuam_ligados_ao_aluno_apos_mudanca(aluno, turma_b):
    RegistroFrequencia.objects.create(aluno=aluno, data=date(2026, 3, 3), presente=True)
    aluno.mudar_turma(turma_b, date(2026, 5, 4))
    assert aluno.frequencias.count() == 1


def test_mudar_para_a_mesma_turma_nao_altera_o_historico(aluno, turma_a):
    aluno.mudar_turma(turma_a, date(2026, 5, 4))
    assert aluno.historico_turmas.count() == 1


def test_mudanca_de_turma_antes_do_inicio_atual_e_recusada(aluno, turma_b):
    with pytest.raises(ValueError):
        aluno.mudar_turma(turma_b, date(2026, 2, 9))


def test_so_pode_haver_uma_turma_atual(aluno, turma_b):
    falha_no_banco(
        lambda: HistoricoTurma.objects.create(
            aluno=aluno, turma=turma_b, data_inicio=date(2026, 6, 1)
        )
    )


# --- NF007: nenhuma exclusão física -------------------------------------------------


def test_aluno_nao_pode_ser_excluido(aluno):
    with pytest.raises(ExclusaoProibidaError):
        aluno.delete()
    assert Aluno.objects.filter(pk=aluno.pk).exists()


@pytest.mark.parametrize(
    "modelo", [Aluno, Turma, HistoricoTurma, RegistroFrequencia, Alerta, Intervencao, RegraAlerta]
)
def test_exclusao_em_massa_e_recusada(modelo, aluno):
    with pytest.raises(ExclusaoProibidaError):
        modelo.objects.all().delete()


# --- NF008: importação repetida não duplica -----------------------------------------


def test_frequencia_do_mesmo_dia_nao_duplica(aluno):
    RegistroFrequencia.objects.create(aluno=aluno, data=date(2026, 3, 3), presente=True)
    falha_no_banco(
        lambda: RegistroFrequencia.objects.create(
            aluno=aluno, data=date(2026, 3, 3), presente=False
        )
    )


def test_simulado_da_mesma_area_e_ciclo_nao_duplica(aluno, ciclo):
    ResultadoSimulado.objects.create(
        aluno=aluno, ciclo=ciclo, area="MATEMATICA", nota_tri=Decimal("612.4"), acertos=28
    )
    falha_no_banco(
        lambda: ResultadoSimulado.objects.create(
            aluno=aluno, ciclo=ciclo, area="MATEMATICA", nota_tri=Decimal("500.0"), acertos=20
        )
    )


def test_redacao_do_mesmo_tema_nao_duplica(aluno):
    ResultadoRedacao.objects.create(aluno=aluno, tema_semana=date(2026, 3, 3), entregue=False)
    falha_no_banco(
        lambda: ResultadoRedacao.objects.create(
            aluno=aluno, tema_semana=date(2026, 3, 3), entregue=False
        )
    )


def test_turma_com_mesmo_nome_no_mesmo_ano_nao_duplica(turma_a):
    falha_no_banco(lambda: Turma.objects.create(nome="Turma A", ano=2026))
    assert Turma.objects.create(nome="Turma A", ano=2027)


# --- Regras de consistência dos registros -------------------------------------------


@pytest.mark.regras
@pytest.mark.parametrize(
    ("presente", "justificada", "falta"),
    [(True, False, False), (False, False, True), (False, True, False)],
)
def test_ausencia_justificada_conta_como_presenca(aluno, presente, justificada, falta):
    """RN001 e RN002: só a ausência sem justificativa é falta."""
    registro = RegistroFrequencia(
        aluno=aluno, data=date(2026, 3, 3), presente=presente, justificada=justificada
    )
    assert registro.eh_falta is falta


def test_ausente_no_simulado_nao_tem_nota(aluno, ciclo):
    """RN009: ausente no simulado não é avaliado em desempenho."""
    ResultadoSimulado.objects.create(aluno=aluno, ciclo=ciclo, area="HUMANAS", presente=False)
    falha_no_banco(
        lambda: ResultadoSimulado.objects.create(
            aluno=aluno, ciclo=ciclo, area="NATUREZA", presente=False, acertos=10
        )
    )


def test_redacao_nao_entregue_nao_tem_nota(aluno):
    falha_no_banco(
        lambda: ResultadoRedacao.objects.create(
            aluno=aluno, tema_semana=date(2026, 3, 3), entregue=False, nota_c1=120
        )
    )


def test_competencia_da_redacao_vai_ate_200(aluno):
    falha_no_banco(
        lambda: ResultadoRedacao.objects.create(
            aluno=aluno, tema_semana=date(2026, 3, 3), entregue=True, nota_c1=201
        )
    )


def test_nota_total_da_redacao(aluno):
    redacao = ResultadoRedacao(
        aluno=aluno,
        tema_semana=date(2026, 3, 3),
        entregue=True,
        nota_c1=160,
        nota_c2=120,
        nota_c3=140,
        nota_c4=180,
        nota_c5=100,
    )
    assert redacao.nota_total == 700
    redacao.nota_c5 = None
    assert redacao.nota_total is None


def test_ciclo_termina_depois_de_comecar():
    falha_no_banco(
        lambda: CicloCalendario.objects.create(
            data_inicio=date(2026, 3, 16), data_fim=date(2026, 3, 2)
        )
    )


# --- Alertas, regras e intervenções -------------------------------------------------


@pytest.fixture
def regra():
    return RegraAlerta.objects.create(
        tipo_regra=RegraAlerta.Tipo.FREQUENCIA,
        limiar=Decimal("3"),
        descricao="Sinaliza o aluno com 3 ou mais faltas não justificadas na semana.",
    )


@pytest.fixture
def alerta(aluno, regra):
    return Alerta.objects.create(
        aluno=aluno,
        tipo=Alerta.Tipo.FREQUENCIA,
        motivo="3 faltas não justificadas na semana de 02/03/2026.",
        data_geracao=datetime(2026, 3, 9, 7, 0, tzinfo=SP),
        regra=regra,
    )


def test_alerta_sem_motivo_e_recusado(aluno):
    """NF004: todo alerta exibe tipo e motivo."""
    falha_no_banco(
        lambda: Alerta.objects.create(
            aluno=aluno,
            tipo=Alerta.Tipo.DESEMPENHO,
            motivo="",
            data_geracao=datetime(2026, 3, 16, 7, 0, tzinfo=SP),
        )
    )


def test_so_uma_regra_ativa_por_tipo(regra):
    falha_no_banco(
        lambda: RegraAlerta.objects.create(
            tipo_regra=RegraAlerta.Tipo.FREQUENCIA, limiar=Decimal("4"), descricao="Outra."
        )
    )
    regra.ativa = False
    regra.save()
    assert RegraAlerta.objects.create(
        tipo_regra=RegraAlerta.Tipo.FREQUENCIA, limiar=Decimal("4"), descricao="Novo limiar."
    )


def test_intervencao_ligada_a_alerta_com_desfecho_posterior(aluno, alerta, diretor):
    intervencao = Intervencao.objects.create(
        aluno=aluno,
        alerta=alerta,
        usuario=diretor,
        responsavel="Diretor de RH",
        tipo=Intervencao.Tipo.CONVERSA,
        data=date(2026, 3, 10),
        descricao="Conversa sobre as faltas da semana.",
    )
    assert intervencao.desfecho == ""

    intervencao.desfecho = Intervencao.Desfecho.EM_ACOMPANHAMENTO
    intervencao.save()
    assert alerta.intervencoes.get().desfecho == "EM_ACOMPANHAMENTO"


def test_intervencao_sem_alerta(aluno, diretor):
    """Fluxo secundário do RF019."""
    intervencao = Intervencao.objects.create(
        aluno=aluno,
        usuario=diretor,
        responsavel="Diretor de Desempenho",
        tipo=Intervencao.Tipo.CONTATO,
        data=date(2026, 3, 10),
        descricao="Contato por telefone.",
    )
    assert intervencao.alerta is None


def test_intervencao_e_alerta_devem_ser_do_mesmo_aluno(alerta, turma_a, diretor):
    outro = Aluno.objects.create(
        matricula="S260002",
        nome="Aluno Sintético Dois",
        data_ingresso=date(2026, 2, 9),
        turma=turma_a,
    )
    with pytest.raises(ValueError):
        Intervencao.objects.create(
            aluno=outro,
            alerta=alerta,
            usuario=diretor,
            responsavel="Diretor de RH",
            tipo=Intervencao.Tipo.CONTATO,
            data=date(2026, 3, 10),
            descricao="Contato.",
        )


def test_representacoes_textuais(aluno, ciclo, alerta, regra, diretor):
    intervencao = Intervencao.objects.create(
        aluno=aluno,
        usuario=diretor,
        responsavel="Diretor de RH",
        tipo=Intervencao.Tipo.CONTATO,
        data=date(2026, 3, 10),
        descricao="Contato.",
    )
    textos = [
        str(aluno),
        str(aluno.turma),
        str(aluno.historico_turmas.get()),
        str(ciclo),
        str(RegistroFrequencia(aluno=aluno, data=date(2026, 3, 3), presente=False)),
        str(ResultadoSimulado(aluno=aluno, ciclo=ciclo, area="MATEMATICA")),
        str(ResultadoRedacao(aluno=aluno, tema_semana=date(2026, 3, 3), entregue=False)),
        str(alerta),
        str(regra),
        str(intervencao),
    ]
    assert all(textos)
