"""Telas de cadastro de alunos e turmas (RF006, RN003, RN011, NF007, NF009)."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import Aluno, HistoricoTurma, RegistroAlteracao, Turma
from ingestao import leitura

pytestmark = pytest.mark.django_db

PEQUENA = Path(__file__).parent / "dados_sinteticos" / "pequena" / "2026" / "cadastro_alunos.csv"
D = date(2026, 2, 2)


@pytest.fixture
def aluno(turma_a):
    return Aluno.objects.create(
        matricula="S1", nome="Ana Sintética", data_ingresso=D, turma=turma_a
    )


@pytest.fixture
def turma_b():
    return Turma.objects.create(nome="Turma B", ano=2026)


def _rotas_escrita(aluno, turma_a):
    return [
        reverse("web:aluno_novo"),
        reverse("web:aluno_editar", args=[aluno.matricula]),
        reverse("web:turma_nova"),
        reverse("web:turma_editar", args=[turma_a.pk]),
        reverse("web:cadastro_importar"),
    ]


def _rotas_leitura(turma_a):
    return [
        reverse("web:alunos"),
        reverse("web:turmas"),
        reverse("web:turma_detalhe", args=[turma_a.pk]),
    ]


def test_membro_recebe_403_nas_rotas_de_escrita(client, membro, aluno, turma_a):
    client.force_login(membro)
    for url in _rotas_escrita(aluno, turma_a):
        assert client.get(url).status_code == 403, url
        assert client.post(url, {"nome": "x"}).status_code == 403, url
    assert Aluno.objects.count() == 1


def test_membro_le_listas(client, membro, aluno, turma_a):
    client.force_login(membro)
    for url in _rotas_leitura(turma_a):
        resp = client.get(url)
        assert resp.status_code == 200, url
    assert "Ana Sintética" in client.get(reverse("web:alunos")).content.decode()
    assert (
        "Ana Sintética"
        in client.get(reverse("web:turma_detalhe", args=[turma_a.pk])).content.decode()
    )
    html = client.get(reverse("web:alunos")).content.decode()
    assert "Editar" not in html and "Novo aluno" not in html


def test_anonimo_vai_para_login(client, aluno, turma_a):
    for url in _rotas_escrita(aluno, turma_a) + _rotas_leitura(turma_a):
        resp = client.get(url)
        assert resp.status_code == 302 and reverse("web:login") in resp["Location"], url


def test_criar_aluno_abre_historico(cliente_diretor, turma_a):
    resp = cliente_diretor.post(
        reverse("web:aluno_novo"),
        {
            "matricula": "S9",
            "nome": "Novo  Aluno",
            "data_ingresso": "2026-02-09",
            "turma": turma_a.pk,
        },
    )
    assert resp.status_code == 302
    aluno = Aluno.objects.get(pk="S9")
    assert aluno.nome == "Novo Aluno" and aluno.situacao == "ATIVO"
    assert aluno.historico_turmas.get().data_inicio == date(2026, 2, 9)


def test_matricula_existente_rejeitada(cliente_diretor, aluno, turma_a):
    resp = cliente_diretor.post(
        reverse("web:aluno_novo"),
        {"matricula": "S1", "nome": "Outro", "data_ingresso": "2026-02-09", "turma": turma_a.pk},
    )
    assert resp.status_code == 200 and "Já existe" in resp.content.decode()
    assert Aluno.objects.get(pk="S1").nome == "Ana Sintética"


def _editar(client, aluno, **dados):
    base = {
        "nome": aluno.nome,
        "data_ingresso": aluno.data_ingresso.isoformat(),
        "turma": aluno.turma_id,
        "situacao": aluno.situacao,
        "data_saida": aluno.data_saida.isoformat() if aluno.data_saida else "",
        "data_mudanca": "",
    }
    base.update(dados)
    return client.post(reverse("web:aluno_editar", args=[aluno.matricula]), base)


def test_matricula_nao_editavel(cliente_diretor, aluno):
    resp = _editar(cliente_diretor, aluno, matricula="S2", nome="Ana Nova")
    assert resp.status_code == 302
    assert Aluno.objects.filter(pk="S1").exists() and not Aluno.objects.filter(pk="S2").exists()


def test_editar_nome_registra_auditoria(cliente_diretor, diretor, aluno):
    _editar(cliente_diretor, aluno, nome="Ana Corrigida")
    reg = RegistroAlteracao.objects.get(campo="nome")
    assert (reg.autor, reg.objeto_id, reg.valor_anterior) == (diretor, "S1", "Ana Sintética")
    assert reg.valor_novo == "Ana Corrigida"
    assert RegistroAlteracao.objects.count() == 1


def test_mudar_turma_exige_data(cliente_diretor, aluno, turma_b):
    resp = _editar(cliente_diretor, aluno, turma=turma_b.pk)
    assert resp.status_code == 200
    aluno.refresh_from_db()
    assert aluno.turma != turma_b and aluno.historico_turmas.count() == 1


def test_mudar_turma_data_no_inicio_e_rejeitada_e_no_dia_seguinte_passa(
    cliente_diretor, aluno, turma_b
):
    assert (
        _editar(cliente_diretor, aluno, turma=turma_b.pk, data_mudanca=D.isoformat()).status_code
        == 200
    )
    resp = _editar(
        cliente_diretor, aluno, turma=turma_b.pk, data_mudanca=(D + timedelta(days=1)).isoformat()
    )
    assert resp.status_code == 302


def test_mudar_turma_fecha_periodo(cliente_diretor, aluno, turma_a, turma_b):
    _editar(cliente_diretor, aluno, turma=turma_b.pk, data_mudanca="2026-03-02")
    aluno.refresh_from_db()
    assert aluno.turma == turma_b
    periodos = list(HistoricoTurma.objects.filter(aluno=aluno).order_by("data_inicio"))
    assert [p.turma for p in periodos] == [turma_a, turma_b]
    assert periodos[0].data_fim == date(2026, 3, 2)
    assert RegistroAlteracao.objects.filter(campo="turma").count() == 1


def test_editar_situacao_e_data_saida_com_auditoria(cliente_diretor, aluno):
    resp = _editar(cliente_diretor, aluno, situacao="EVADIDO", data_saida="2026-05-01")
    assert resp.status_code == 302
    aluno.refresh_from_db()
    assert (aluno.situacao, aluno.data_saida) == ("EVADIDO", date(2026, 5, 1))
    assert set(RegistroAlteracao.objects.values_list("campo", flat=True)) == {
        "situacao",
        "data_saida",
    }


@pytest.mark.parametrize(
    "dados",
    [
        {"situacao": "ATIVO", "data_saida": "2026-05-01"},
        {"situacao": "DESLIGADO", "data_saida": ""},
        {"situacao": "EVADIDO", "data_saida": "2026-02-01"},
    ],
)
def test_situacao_invalida_e_rejeitada(cliente_diretor, aluno, dados):
    assert _editar(cliente_diretor, aluno, **dados).status_code == 200
    assert Aluno.objects.get(pk="S1").situacao == "ATIVO"


def test_saida_no_dia_do_ingresso_passa(cliente_diretor, aluno):
    assert (
        _editar(cliente_diretor, aluno, situacao="DESLIGADO", data_saida="2026-02-02").status_code
        == 302
    )


def test_corrigir_ingresso_pela_edicao(cliente_diretor, aluno):
    _editar(cliente_diretor, aluno, data_ingresso="2026-01-30")
    aluno.refresh_from_db()
    assert aluno.data_ingresso == date(2026, 1, 30)
    assert aluno.historico_turmas.get().data_inicio == date(2026, 1, 30)
    assert RegistroAlteracao.objects.filter(campo="data_ingresso").exists()


def test_invalido_some_da_lista_por_padrao(cliente_diretor, aluno):
    _editar(cliente_diretor, aluno, situacao="INVALIDO")
    url = reverse("web:alunos")
    assert "S1" not in cliente_diretor.get(url).content.decode()
    assert "S1" in cliente_diretor.get(url, {"situacao": "TODAS"}).content.decode()
    assert "S1" in cliente_diretor.get(url, {"situacao": "INVALIDO"}).content.decode()


def test_filtros_da_lista(cliente_diretor, aluno, turma_b):
    Aluno.objects.create(matricula="S2", nome="Beto Sintético", data_ingresso=D, turma=turma_b)
    url = reverse("web:alunos")
    html = cliente_diretor.get(url, {"turma": turma_b.pk}).content.decode()
    assert "S2" in html and "S1" not in html


def test_turma_criar_editar_com_auditoria(cliente_diretor, turma_a):
    resp = cliente_diretor.post(reverse("web:turma_nova"), {"nome": "Turma Z", "ano": 2026})
    assert resp.status_code == 302 and Turma.objects.filter(nome="Turma Z").exists()
    dup = cliente_diretor.post(reverse("web:turma_nova"), {"nome": "turma a", "ano": 2026})
    assert dup.status_code == 200
    cliente_diretor.post(
        reverse("web:turma_editar", args=[turma_a.pk]), {"nome": "Turma AA", "ano": 2026}
    )
    assert RegistroAlteracao.objects.get(campo="nome").valor_novo == "Turma AA"


def _upload(conteudo, nome="cad.csv"):
    return SimpleUploadedFile(nome, conteudo)


def _form(arquivo, acao):
    return {"arquivo": arquivo, "ano": 2026, "data_mudanca": "2026-03-02", "acao": acao}


def test_importar_conferir_nao_grava(cliente_diretor):
    resp = cliente_diretor.post(
        reverse("web:cadastro_importar"), _form(_upload(PEQUENA.read_bytes()), "conferir")
    )
    assert resp.status_code == 200 and "nada foi gravado" in resp.content.decode()
    assert not Aluno.objects.exists() and not Turma.objects.exists()


def test_importar_gravar(cliente_diretor):
    resp = cliente_diretor.post(
        reverse("web:cadastro_importar"), _form(_upload(PEQUENA.read_bytes()), "importar")
    )
    assert resp.status_code == 200 and "Importação concluída" in resp.content.decode()
    assert Aluno.objects.count() == 20 and Turma.objects.count() == 5


def test_importar_arquivo_invalido_mostra_erro(cliente_diretor):
    resp = cliente_diretor.post(
        reverse("web:cadastro_importar"), _form(_upload(b"matricula;turma\nS1;A\n"), "importar")
    )
    assert resp.status_code == 200 and "Coluna obrigatória ausente" in resp.content.decode()
    resp = cliente_diretor.post(
        reverse("web:cadastro_importar"), _form(_upload(b"x", "a.txt"), "importar")
    )
    assert resp.status_code == 200 and not Aluno.objects.exists()


def test_importar_limite_de_tamanho(cliente_diretor, monkeypatch):
    conteudo = PEQUENA.read_bytes()
    monkeypatch.setattr(leitura, "TAMANHO_MAXIMO", len(conteudo))
    url = reverse("web:cadastro_importar")
    ok = cliente_diretor.post(url, _form(_upload(conteudo), "conferir"))
    assert "Alunos criados: 20" in ok.content.decode()
    estouro = cliente_diretor.post(url, _form(_upload(conteudo + b" "), "conferir"))
    assert "tamanho máximo" in estouro.content.decode()


def test_nao_existe_rota_de_exclusao():
    from web.urls import urlpatterns

    nomes = [str(p.pattern) + (p.name or "") for p in urlpatterns]
    assert not [n for n in nomes if any(x in n for x in ("exclu", "delet", "apag", "remov"))]
