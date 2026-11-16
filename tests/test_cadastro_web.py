"""Telas de cadastro de alunos e turmas (RF006, RN003, RN011, NF007, NF009)."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import Aluno, HistoricoTurma, RegistroAlteracao, RegistroImportacao, Turma
from ingestao import leitura
from tests.conftest import importar_em_dois_passos

pytestmark = pytest.mark.django_db

PEQUENA = Path(__file__).parent / "dados_sinteticos" / "pequena" / "2026" / "cadastro_alunos.csv"
D = date(2026, 2, 2)


@pytest.fixture
def aluno(turma_a):
    return Aluno.objects.create(
        matricula="S260001", nome="Ana Sintética", data_ingresso=D, turma=turma_a
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
            "matricula": "S260009",
            "nome": "Novo  Aluno",
            "data_ingresso": "2026-02-09",
            "turma": turma_a.pk,
        },
    )
    assert resp.status_code == 302
    aluno = Aluno.objects.get(pk="S260009")
    assert aluno.nome == "Novo Aluno" and aluno.situacao == "ATIVO"
    assert aluno.historico_turmas.get().data_inicio == date(2026, 2, 9)


def test_matricula_existente_rejeitada(cliente_diretor, aluno, turma_a):
    resp = cliente_diretor.post(
        reverse("web:aluno_novo"),
        {
            "matricula": "S260001",
            "nome": "Outro",
            "data_ingresso": "2026-02-09",
            "turma": turma_a.pk,
        },
    )
    assert resp.status_code == 200 and "Já existe" in resp.content.decode()
    assert Aluno.objects.get(pk="S260001").nome == "Ana Sintética"


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
    resp = _editar(cliente_diretor, aluno, matricula="S260002", nome="Ana Nova")
    assert resp.status_code == 302
    assert (
        Aluno.objects.filter(pk="S260001").exists()
        and not Aluno.objects.filter(pk="S260002").exists()
    )


def test_editar_nome_registra_auditoria(cliente_diretor, diretor, aluno):
    _editar(cliente_diretor, aluno, nome="Ana Corrigida")
    reg = RegistroAlteracao.objects.get(campo="nome")
    assert (reg.autor, reg.objeto_id, reg.valor_anterior) == (diretor, "S260001", "Ana Sintética")
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
    assert Aluno.objects.get(pk="S260001").situacao == "ATIVO"


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
    assert "S260001" not in cliente_diretor.get(url).content.decode()
    assert "S260001" in cliente_diretor.get(url, {"situacao": "TODAS"}).content.decode()
    assert "S260001" in cliente_diretor.get(url, {"situacao": "INVALIDO"}).content.decode()


def test_filtros_da_lista(cliente_diretor, aluno, turma_b):
    Aluno.objects.create(matricula="S260002", nome="Beto Sintético", data_ingresso=D, turma=turma_b)
    url = reverse("web:alunos")
    html = cliente_diretor.get(url, {"turma": turma_b.pk}).content.decode()
    assert "S260002" in html and "S260001" not in html


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


def _importar(cliente, nome="cad.csv"):
    return importar_em_dois_passos(
        cliente,
        reverse("web:cadastro_importar"),
        lambda acao: _form(_upload(PEQUENA.read_bytes(), nome), acao),
    )


def test_importar_conferir_nao_grava(cliente_diretor):
    resp = cliente_diretor.post(
        reverse("web:cadastro_importar"), _form(_upload(PEQUENA.read_bytes()), "conferir")
    )
    assert resp.status_code == 200 and "nada foi gravado" in resp.content.decode()
    assert not Aluno.objects.exists() and not Turma.objects.exists()


def test_importar_gravar(cliente_diretor):
    resp = _importar(cliente_diretor)
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


def test_membro_baixa_modelos_mas_nao_acessa_importacao(client, membro):
    client.force_login(membro)
    for nome in ("cadastro_modelo_xlsx", "cadastro_modelo_csv"):
        assert client.get(reverse(f"web:{nome}")).status_code == 200, nome
    assert client.get(reverse("web:cadastro_importar")).status_code == 403
    assert "Importar cadastro" not in client.get(reverse("web:alunos")).content.decode()


def test_membro_nao_importa_nada_e_nada_e_gravado(client, membro):
    client.force_login(membro)
    url = reverse("web:cadastro_importar")
    for acao in ("conferir", "importar"):
        assert client.post(url, _form(_upload(PEQUENA.read_bytes()), acao)).status_code == 403
    assert not RegistroImportacao.objects.exists() and not Aluno.objects.exists()


def test_diretor_importa_e_registro_leva_o_autor(cliente_diretor, diretor):
    url = reverse("web:cadastro_importar")
    cliente_diretor.post(url, _form(_upload(PEQUENA.read_bytes()), "conferir"))
    assert not RegistroImportacao.objects.exists()
    _importar(cliente_diretor, "../x/cad.csv")
    reg = RegistroImportacao.objects.get()
    assert reg.autor == diretor and reg.tipo == "CADASTRO" and reg.ano == 2026
    assert reg.nome_arquivo == "cad.csv" and reg.tamanho_bytes == len(PEQUENA.read_bytes())
    assert reg.criados == 20 and reg.turmas_criadas == 5
    assert reg.data_mudanca == date(2026, 3, 2)


def test_cadastro_manual_exige_matricula_do_ano_da_turma(cliente_diretor, turma_a):
    base = {"nome": "Novo", "data_ingresso": "2026-02-09", "turma": turma_a.pk}
    for ruim, msg in (("2632001", "fora do padrão"), ("S250001", "outro ano letivo")):
        resp = cliente_diretor.post(reverse("web:aluno_novo"), {**base, "matricula": ruim})
        assert resp.status_code == 200 and msg in resp.content.decode(), ruim
    ok = cliente_diretor.post(reverse("web:aluno_novo"), {**base, "matricula": "2630042"})
    assert ok.status_code == 302 and Aluno.objects.filter(pk="2630042").exists()


def test_edicao_so_aceita_turma_do_mesmo_ano(cliente_diretor, aluno):
    outra = Turma.objects.create(nome="Turma 2027", ano=2027)
    resp = _editar(cliente_diretor, aluno, turma=outra.pk, data_mudanca="2026-03-02")
    assert resp.status_code == 200
    aluno.refresh_from_db()
    assert aluno.turma.ano == 2026 and aluno.historico_turmas.count() == 1


def test_registro_nao_contem_nome_de_aluno(cliente_diretor):
    _importar(cliente_diretor)
    nomes = list(Aluno.objects.values_list("nome", flat=True))
    reg = RegistroImportacao.objects.get()
    texto = " ".join(str(v) for v in vars(reg).values())
    assert not any(n in texto for n in nomes)


def test_importacoes_so_diretor(client, membro):
    client.force_login(membro)
    assert client.get(reverse("web:importacoes")).status_code == 403
    assert "Importações" not in client.get(reverse("web:alunos")).content.decode()


def test_importacoes_lista_ordenada_com_autor_e_filtro(cliente_diretor, diretor, membro):
    for autor, nome in ((diretor, "a.csv"), (membro, "b.csv"), (diretor, "c.csv")):
        RegistroImportacao.objects.create(
            autor=autor, tipo="CADASTRO", nome_arquivo=nome, tamanho_bytes=1, ano=2026
        )
    resp = cliente_diretor.get(reverse("web:importacoes"))
    html = resp.content.decode()
    assert html.index("c.csv") < html.index("b.csv") < html.index("a.csv")
    assert "membro" in html and "Importações" in html
    filtrada = cliente_diretor.get(reverse("web:importacoes") + "?usuario=membro").content.decode()
    assert "b.csv" in filtrada and "a.csv" not in filtrada


def test_registro_importacao_sem_exclusao_nem_edicao(diretor):
    from core.historico import ExclusaoProibidaError
    from web.urls import urlpatterns

    reg = RegistroImportacao.objects.create(
        autor=diretor, tipo="CADASTRO", nome_arquivo="a.csv", tamanho_bytes=1, ano=2026
    )
    with pytest.raises(ExclusaoProibidaError):
        reg.delete()
    nomes = [
        str(p.pattern) + (p.name or "") for p in urlpatterns if "importacoes" in str(p.pattern)
    ]
    assert nomes == ["importacoes/importacoes"]
