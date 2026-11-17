"""Relatório dos alunos beneficiados por auxílios (RF021, SM #80, opção A).

Base sintética (NF017). A lista de beneficiados nunca é gravada, e o bloco agregado não traz
nome nem matrícula (RN013, RN014).
"""

import io
import logging
import re

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import Aluno
from inteligencia import painel
from relatorios import auxilios

pytestmark = pytest.mark.django_db
URL = "web:auxilios"


@pytest.fixture
def base(diretor):
    from ingestao.demonstracao import carregar

    carregar(2026, autor=diretor)


def _csv(matriculas, cabecalho="matricula"):
    texto = "\n".join([cabecalho, *matriculas]) + "\n"
    return SimpleUploadedFile("lista.csv", texto.encode(), content_type="text/csv")


def _enviar(cliente, matriculas, ano=2026, **kw):
    return cliente.post(reverse(URL), {"arquivo": _csv(matriculas, **kw), "ano": ano})


def _contagens():
    return {m._meta.label: m.objects.count() for m in apps.get_models()}


def _matriculas(n=3):
    return list(Aluno.objects.order_by("matricula").values_list("matricula", flat=True)[:n])


def _bloco_agregado(html):
    return html.split("Lista nominal")[0]


def test_membro_recebe_403_e_anonimo_vai_para_login(client, membro, base):
    url = reverse(URL)
    assert client.get(url).status_code == 302
    client.force_login(membro)
    assert client.get(url).status_code == 403
    resp = client.post(url, {"arquivo": _csv(_matriculas()), "ano": 2026})
    assert resp.status_code == 403
    assert client.get(reverse("web:auxilios_modelo", args=["csv"])).status_code == 403


def test_nada_e_gravado(cliente_diretor, base, tmp_path, settings, caplog):
    settings.MEDIA_ROOT = tmp_path
    antes = _contagens()
    sessao_antes = set(cliente_diretor.session.keys())
    with caplog.at_level(logging.DEBUG):
        resp = _enviar(cliente_diretor, [*_matriculas(), "S269999"])
    assert resp.status_code == 200 and resp.context["relatorio"].beneficiados.alunos == 3
    assert _contagens() == antes
    assert set(cliente_diretor.session.keys()) == sessao_antes
    assert list(tmp_path.iterdir()) == []
    for matricula in _matriculas():
        assert matricula not in caplog.text


def test_matricula_desconhecida_so_e_contada(cliente_diretor, base):
    antes = _contagens()
    resp = _enviar(cliente_diretor, [*_matriculas(2), "S269998", "S269999"])
    rel = resp.context["relatorio"]
    assert (rel.lidas, rel.beneficiados.alunos, rel.sem_aluno) == (4, 2, 2)
    assert "S269998" not in resp.content.decode()
    assert _contagens() == antes  # nem pendência nem trilha


def test_matricula_de_outro_ano_e_invalida_sao_recusadas(cliente_diretor, base):
    resp = _enviar(cliente_diretor, [_matriculas(1)[0], "S250001", "abc", _matriculas(1)[0]])
    rel = resp.context["relatorio"]
    assert rel.beneficiados.alunos == 1
    assert rel.recusadas == [
        (3, "matrícula de outro ano letivo"),
        (4, "matrícula fora do padrão"),
        (5, "matrícula repetida no arquivo"),
    ]
    html = resp.content.decode()
    assert "S250001" not in html and "abc" not in html


def test_agregados_conferem_com_painel_e_consultas(cliente_diretor, base):
    ref = painel.referencia(2026)
    _, total = painel.situacao(ref)
    marcados = _matriculas(5)
    rel = _enviar(cliente_diretor, marcados).context["relatorio"]
    b, d = rel.beneficiados, rel.demais
    assert b.alunos + d.alunos == total.total_alunos
    assert b.frequencia + d.frequencia == total.frequencia
    assert b.participacao.registradas + d.participacao.registradas == total.participacao.registradas
    for chave in ("queda", "estagnado", "evolucao", "sem_avaliacao"):
        esperado = len(total.alunos[chave]) if chave != "sem_avaliacao" else None
        if esperado is not None:
            assert b.classificacao[chave] + d.classificacao[chave] == esperado
    assert sum(b.classificacao.values()) == b.alunos
    alertas = painel.alertas_ativos(ref)
    com_alerta = {a.aluno_id for lista in alertas.values() for a in lista}
    assert b.alunos_com_alerta + d.alunos_com_alerta == len(com_alerta)


def test_intervencoes_por_desfecho(cliente_diretor, diretor, base):
    from datetime import date

    from core.models import Intervencao

    alvo, outro = Aluno.objects.order_by("matricula")[:2]
    for aluno, desfecho in ((alvo, "RESOLVIDO"), (alvo, ""), (outro, "SEM_RETORNO")):
        Intervencao.objects.create(
            aluno=aluno, usuario=diretor, responsavel="Resp", tipo="CONTATO",
            data=date(2026, 5, 4), descricao="x", desfecho=desfecho,
        )  # fmt: skip
    rel = _enviar(cliente_diretor, [alvo.matricula]).context["relatorio"]
    assert rel.beneficiados.total_intervencoes == 2
    assert rel.beneficiados.intervencoes["Resolvido"] == 1
    assert rel.beneficiados.intervencoes[auxilios.SEM_DESFECHO] == 1
    assert rel.demais.intervencoes["Sem retorno"] == 1


def test_bloco_agregado_nao_tem_nome_nem_matricula(cliente_diretor, base):
    resp = _enviar(cliente_diretor, _matriculas(4))
    html = resp.content.decode()
    agregado = _bloco_agregado(html)
    assert "Resumo para a prestação de contas" in agregado
    assert not re.search(r"S26\d{4}", agregado)
    for nome in Aluno.objects.values_list("nome", flat=True):
        assert nome not in agregado
    # a lista nominal, separada, traz os beneficiados
    nominal = html.split("Lista nominal")[1]
    assert _matriculas(1)[0] in nominal


def test_erro_de_arquivo_sem_conteudo_de_celulas(cliente_diretor, base):
    arquivo = SimpleUploadedFile("lista.csv", b"segredo;outro\nvalor-secreto;x\n")
    resp = cliente_diretor.post(reverse(URL), {"arquivo": arquivo, "ano": 2026})
    assert resp.status_code == 200 and resp.context["form"].errors
    html = resp.content.decode()
    assert "segredo" not in html and "valor-secreto" not in html
    resp = cliente_diretor.post(
        reverse(URL), {"arquivo": SimpleUploadedFile("lista.txt", b"x"), "ano": 2026}
    )
    assert resp.context["form"].errors


def test_arquivo_grande_e_recusado_sem_ler(cliente_diretor, base):
    grande = SimpleUploadedFile("lista.csv", b"matricula\n" + b"S260001\n" * 200_000)
    resp = cliente_diretor.post(reverse(URL), {"arquivo": grande, "ano": 2026})
    assert resp.status_code == 400
    assert "relatorio" not in resp.context


def test_xlsx_e_modelo_para_download(cliente_diretor, base):
    resp = cliente_diretor.get(reverse("web:auxilios_modelo", args=["xlsx"]))
    assert resp.status_code == 200 and "attachment" in resp["Content-Disposition"]
    arquivo = SimpleUploadedFile("modelo.xlsx", resp.content)
    resp = cliente_diretor.post(reverse(URL), {"arquivo": arquivo, "ano": 2026})
    rel = resp.context["relatorio"]
    assert rel.lidas == 2  # as duas matrículas sintéticas do modelo
    assert cliente_diretor.get(reverse("web:auxilios_modelo", args=["pdf"])).status_code == 404
    assert cliente_diretor.get(reverse("web:auxilios_modelo", args=["csv"])).status_code == 200


def test_sem_dados_no_ano(cliente_diretor, turma_a):
    Aluno(matricula="S260001", nome="Aluno Sintético", turma=turma_a,
          data_ingresso="2026-01-05").save()  # fmt: skip
    resp = _enviar(cliente_diretor, ["S260001"])
    rel = resp.context["relatorio"]
    assert rel.beneficiados.alunos == 1 and rel.beneficiados.frequencia.dias == 0
    assert "sem dados" in resp.content.decode()


def test_tela_inicial_tem_aviso_e_modelo(cliente_diretor):
    html = cliente_diretor.get(reverse(URL)).content.decode()
    assert "nada é gravado" in html and "SM #80" in html
    assert "Baixar modelo (.xlsx)" in html and "Baixar modelo (.csv)" in html


def test_leitura_em_memoria_com_arquivo_de_bytes():
    # `matriculas_do_arquivo` só recebe linhas já lidas: nenhum caminho de arquivo envolvido.
    from ingestao.leitura import ler_tabela

    linhas = ler_tabela(io.BytesIO(b"rm\nS260001\n"), "x.csv", colunas=auxilios.COLUNAS)
    assert auxilios.matriculas_do_arquivo(linhas, 2026) == ({"S260001"}, [])
