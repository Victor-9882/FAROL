"""Gestão de usuários e perfis pelo Diretor, com auditoria (RF002, NF009, NF019)."""

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.urls import reverse

from core.auditoria import historico_de, registrar_alteracoes
from core.historico import ExclusaoProibidaError
from core.models import RegistroAlteracao

SENHA = "senha-sintetica-123"  # nosec: dado de teste, sem relação com contas reais
Usuario = get_user_model()


@pytest.fixture
def diretor(db):
    return Usuario.objects.create_user("diretor", "diretor@exemplo.org", SENHA, perfil="DIRETOR")


@pytest.fixture
def membro(db):
    return Usuario.objects.create_user("membro", "membro@exemplo.org", SENHA)


@pytest.fixture
def cliente_diretor(client, diretor):
    client.force_login(diretor)
    return client


def _editar(client, alvo, **dados):
    base = {
        "first_name": alvo.first_name,
        "last_name": alvo.last_name,
        "email": alvo.email,
        "perfil": alvo.perfil,
        "is_active": "on" if alvo.is_active else "",
    }
    base.update(dados)
    if not base["is_active"]:
        del base["is_active"]  # checkbox ausente significa False
    return client.post(reverse("web:usuario_editar", args=[alvo.pk]), base)


ROTAS = ["web:usuarios", "web:usuario_novo", "web:usuario_editar", "web:usuario_link_senha"]


@pytest.mark.parametrize("nome", ROTAS)
def test_rotas_de_usuarios_negam_membro_e_anonimo(client, membro, nome):
    args = [membro.pk] if nome in ("web:usuario_editar", "web:usuario_link_senha") else []
    url = reverse(nome, args=args)
    assert client.get(url).status_code == 302
    assert client.post(url).status_code == 302
    assert reverse("web:login") in client.get(url)["Location"]
    client.force_login(membro)
    assert client.get(url).status_code in (403, 405)
    assert client.post(url, {"username": "x"}).status_code == 403
    assert Usuario.objects.count() == 1


def test_membro_nao_cria_usuario(client, membro):
    client.force_login(membro)
    client.post(reverse("web:usuario_novo"), {"username": "novo", "email": "n@exemplo.org"})
    assert not Usuario.objects.filter(username="novo").exists()


@pytest.mark.parametrize("perfil", ["DIRETOR", "MEMBRO"])
def test_diretor_cria_usuario_com_o_perfil_escolhido(cliente_diretor, diretor, perfil):
    resp = cliente_diretor.post(
        reverse("web:usuario_novo"),
        {
            "username": "novo",
            "first_name": "Novo",
            "last_name": "Usuario",
            "email": "Novo@Exemplo.org",
            "perfil": perfil,
            "is_staff": "on",
            "is_superuser": "on",
        },
    )
    novo = Usuario.objects.get(username="novo")
    assert resp.status_code == 302
    assert resp["Location"] == reverse("web:usuario_editar", args=[novo.pk])
    assert novo.perfil == perfil
    assert novo.email == "novo@exemplo.org"
    assert not novo.has_usable_password()
    assert not novo.is_staff and not novo.is_superuser
    regs = RegistroAlteracao.objects.all()
    assert [(r.autor, r.campo, r.valor_anterior, r.valor_novo) for r in regs] == [
        (diretor, "perfil", "", perfil)
    ]


@pytest.mark.parametrize("email", ["membro@exemplo.org", "MEMBRO@Exemplo.org"])
def test_email_duplicado_e_recusado(cliente_diretor, membro, email):
    antes = Usuario.objects.count()
    resp = cliente_diretor.post(
        reverse("web:usuario_novo"), {"username": "outro", "email": email, "perfil": "MEMBRO"}
    )
    assert resp.status_code == 200
    assert resp.context["form"].errors
    assert Usuario.objects.count() == antes


def test_username_duplicado_e_recusado(cliente_diretor, membro):
    antes = Usuario.objects.count()
    resp = cliente_diretor.post(
        reverse("web:usuario_novo"),
        {"username": "membro", "email": "outro@exemplo.org", "perfil": "MEMBRO"},
    )
    assert resp.status_code == 200
    assert Usuario.objects.count() == antes


def test_alteracao_registra_autor_data_e_valor_anterior(cliente_diretor, diretor, membro):
    _editar(cliente_diretor, membro, perfil="DIRETOR")
    reg = RegistroAlteracao.objects.get()
    assert (reg.autor, reg.campo, reg.valor_anterior, reg.valor_novo) == (
        diretor,
        "perfil",
        "MEMBRO",
        "DIRETOR",
    )
    assert reg.modelo == "core.usuario" and reg.objeto_id == str(membro.pk)
    assert reg.criado_em is not None

    membro.refresh_from_db()
    _editar(cliente_diretor, membro, email="novo@exemplo.org", first_name="Ana")
    assert set(RegistroAlteracao.objects.exclude(pk=reg.pk).values_list("campo", flat=True)) == {
        "email",
        "first_name",
    }


def test_salvar_sem_mudanca_nao_gera_registro(cliente_diretor, membro):
    assert _editar(cliente_diretor, membro).status_code == 302
    assert RegistroAlteracao.objects.count() == 0


def test_revogar_desativa_sem_excluir_e_derruba_a_sessao(client, cliente_diretor, membro):
    outro = type(client)()
    outro.force_login(membro)
    assert outro.get(reverse("web:inicio")).status_code == 200
    _editar(cliente_diretor, membro, is_active="")
    membro.refresh_from_db()
    assert Usuario.objects.filter(pk=membro.pk).exists() and not membro.is_active
    reg = RegistroAlteracao.objects.get(campo="is_active")
    assert (reg.valor_anterior, reg.valor_novo) == ("True", "False")
    resp = outro.get(reverse("web:inicio"))
    assert resp.status_code == 302 and reverse("web:login") in resp["Location"]


def test_reativar_devolve_o_acesso(client, cliente_diretor, membro):
    membro.is_active = False
    membro.save()
    _editar(cliente_diretor, membro, is_active="on")
    assert client.login(request=HttpRequest(), username="membro", password=SENHA) is True


@pytest.mark.parametrize("acao", ["rebaixar", "desativar"])
@pytest.mark.parametrize("cenario", ["sozinho", "outro_inativo"])
def test_ultimo_diretor_ativo_nao_perde_o_acesso(cliente_diretor, diretor, acao, cenario):
    if cenario == "outro_inativo":
        Usuario.objects.create_user(
            "d2", "d2@exemplo.org", SENHA, perfil="DIRETOR", is_active=False
        )
    dados = {"perfil": "MEMBRO"} if acao == "rebaixar" else {"is_active": ""}
    resp = _editar(cliente_diretor, diretor, **dados)
    assert resp.status_code == 200
    assert resp.context["form"].non_field_errors()
    diretor.refresh_from_db()
    assert diretor.perfil == "DIRETOR" and diretor.is_active
    assert RegistroAlteracao.objects.count() == 0


@pytest.mark.parametrize("acao", ["rebaixar", "desativar"])
@pytest.mark.parametrize("outro", ["diretor", "superusuario"])
def test_com_dois_diretores_ativos_um_pode_sair(client, diretor, acao, outro):
    if outro == "diretor":
        Usuario.objects.create_user("d2", "d2@exemplo.org", SENHA, perfil="DIRETOR")
    else:
        Usuario.objects.create_superuser("su", "su@exemplo.org", SENHA, perfil="DIRETOR")
    client.force_login(diretor)
    dados = {"perfil": "MEMBRO"} if acao == "rebaixar" else {"is_active": ""}
    assert _editar(client, diretor, **dados).status_code == 302


def test_diretor_que_se_rebaixa_vai_para_o_inicio_e_perde_a_tela(client, diretor):
    Usuario.objects.create_user("d2", "d2@exemplo.org", SENHA, perfil="DIRETOR")
    client.force_login(diretor)
    resp = _editar(client, diretor, perfil="MEMBRO")
    assert resp.status_code == 302 and resp["Location"] == reverse("web:inicio")
    assert client.get(reverse("web:usuarios")).status_code == 403


def _gerar_link(cliente, alvo):
    """Gera o link pelo fluxo real (POST, redirecionamento) e devolve o caminho."""
    resp = cliente.post(reverse("web:usuario_link_senha", args=[alvo.pk]), follow=True)
    link = resp.context["link"]
    return "/" + link.split("://", 1)[1].split("/", 1)[1]


def test_link_de_senha_funciona_uma_unica_vez(client, cliente_diretor, membro):
    membro.set_unusable_password()
    membro.save()
    caminho = _gerar_link(cliente_diretor, membro)
    client.logout()
    resp = client.get(caminho, follow=True)
    assert resp.status_code == 200 and resp.context["validlink"]
    url_final = resp.redirect_chain[-1][0]
    resp = client.post(
        url_final, {"new_password1": "outra-senha-987x", "new_password2": "outra-senha-987x"}
    )
    assert resp.status_code == 302 and resp["Location"] == reverse("web:login")
    assert client.login(request=HttpRequest(), username="membro", password="outra-senha-987x")
    client.logout()
    assert not client.get(caminho, follow=True).context["validlink"]


def test_link_de_usuario_revogado_e_invalido_e_nao_grava_senha(client, cliente_diretor, membro):
    caminho = _gerar_link(cliente_diretor, membro)
    membro.refresh_from_db()
    membro.is_active = False
    membro.save()
    client.logout()
    resp = client.get(caminho, follow=True)
    assert not resp.context["validlink"]
    membro.refresh_from_db()
    assert not membro.has_usable_password()


def test_revogado_entre_abrir_e_enviar_nao_grava_senha(client, cliente_diretor, membro):
    caminho = _gerar_link(cliente_diretor, membro)
    client.logout()
    resp = client.get(caminho, follow=True)
    assert resp.context["validlink"]
    url_final = resp.redirect_chain[-1][0]
    membro.refresh_from_db()
    membro.is_active = False
    membro.save()
    resp = client.post(
        url_final, {"new_password1": "outra-senha-987x", "new_password2": "outra-senha-987x"}
    )
    assert resp.status_code == 200 and not resp.context["validlink"]
    membro.refresh_from_db()
    assert not membro.has_usable_password()


def test_gerar_link_redireciona_e_mostra_uma_vez(cliente_diretor, membro):
    url = reverse("web:usuario_link_senha", args=[membro.pk])
    resp = cliente_diretor.post(url)
    assert resp.status_code == 302 and resp["Location"] == reverse(
        "web:usuario_editar", args=[membro.pk]
    )
    resp = cliente_diretor.get(resp["Location"])
    assert resp.context["link"]
    assert "Cache-Control" in resp and "no-store" in resp["Cache-Control"]
    resp = cliente_diretor.get(reverse("web:usuario_editar", args=[membro.pk]))
    assert resp.context["link"] is None


def test_recarregar_nao_gera_outro_link_nem_registro(client, cliente_diretor, membro):
    resp = cliente_diretor.post(reverse("web:usuario_link_senha", args=[membro.pk]))
    editar = resp["Location"]
    resp = cliente_diretor.get(editar)
    link = resp.context["link"]
    caminho = "/" + link.split("://", 1)[1].split("/", 1)[1]
    cliente_diretor.get(editar)
    assert RegistroAlteracao.objects.filter(campo="senha").count() == 1
    client.logout()
    assert client.get(caminho, follow=True).context["validlink"]


def test_sessao_guarda_so_o_pk(cliente_diretor, membro):
    cliente_diretor.post(reverse("web:usuario_link_senha", args=[membro.pk]))
    assert cliente_diretor.session["link_senha_para"] == membro.pk
    assert "token" not in str(dict(cliente_diretor.session)).lower()


def test_link_nao_aparece_na_edicao_de_outro_usuario(cliente_diretor, membro, diretor):
    outro = Usuario.objects.create_user("outro", "outro@exemplo.org", SENHA)
    cliente_diretor.post(reverse("web:usuario_link_senha", args=[membro.pk]))
    resp = cliente_diretor.get(reverse("web:usuario_editar", args=[outro.pk]))
    assert resp.context["link"] is None


def test_nao_gera_link_para_inativo(client, cliente_diretor, membro):
    membro.is_active = False
    membro.save()
    resp = cliente_diretor.post(reverse("web:usuario_link_senha", args=[membro.pk]))
    assert resp.status_code == 302
    membro.refresh_from_db()
    assert membro.check_password(SENHA)
    assert RegistroAlteracao.objects.count() == 0
    assert "link_senha_para" not in cliente_diretor.session


def test_falha_no_registro_nao_invalida_a_senha(cliente_diretor, membro, monkeypatch):
    def falha(*args, **kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(RegistroAlteracao.objects, "create", falha)
    cliente_diretor.raise_request_exception = False
    cliente_diretor.post(reverse("web:usuario_link_senha", args=[membro.pk]))
    membro.refresh_from_db()
    assert membro.check_password(SENHA)


def test_link_de_senha_so_por_post(cliente_diretor, membro):
    assert (
        cliente_diretor.get(reverse("web:usuario_link_senha", args=[membro.pk])).status_code == 405
    )


def test_gerar_link_invalida_a_senha_atual(client, cliente_diretor, membro):
    cliente_diretor.post(reverse("web:usuario_link_senha", args=[membro.pk]))
    assert not client.login(request=HttpRequest(), username="membro", password=SENHA)
    reg = RegistroAlteracao.objects.get()
    assert reg.valor_novo == "link de definição gerado; senha anterior invalidada"


def test_registro_do_link_nao_guarda_senha_nem_token(cliente_diretor, membro):
    token = _gerar_link(cliente_diretor, membro).rstrip("/").rsplit("/", 1)[1]
    reg = RegistroAlteracao.objects.get()
    assert (reg.campo, reg.valor_anterior, reg.valor_novo) == (
        "senha",
        "",
        "link de definição gerado; senha anterior invalidada",
    )
    assert token not in reg.valor_novo and membro.password not in reg.valor_novo


def test_superusuario_fora_da_tela(cliente_diretor):
    su = Usuario.objects.create_superuser("su", "su@exemplo.org", SENHA)
    assert b"su@exemplo.org" not in cliente_diretor.get(reverse("web:usuarios")).content
    assert cliente_diretor.get(reverse("web:usuario_editar", args=[su.pk])).status_code == 404
    assert cliente_diretor.post(reverse("web:usuario_link_senha", args=[su.pk])).status_code == 404


def test_registro_de_alteracao_nao_pode_ser_excluido(diretor):
    registrar_alteracoes(autor=diretor, objeto=diretor, anteriores={"perfil": "MEMBRO"})
    reg = RegistroAlteracao.objects.get()
    with pytest.raises(ExclusaoProibidaError):
        reg.delete()
    with pytest.raises(ExclusaoProibidaError):
        RegistroAlteracao.objects.all().delete()


def test_registrar_alteracoes_ignora_campo_inalterado(diretor):
    regs = registrar_alteracoes(
        autor=diretor, objeto=diretor, anteriores={"perfil": "DIRETOR", "first_name": None}
    )
    assert regs == [] and RegistroAlteracao.objects.count() == 0


def test_edicao_mostra_o_historico(cliente_diretor, membro):
    _editar(cliente_diretor, membro, perfil="DIRETOR")
    resp = cliente_diretor.get(reverse("web:usuario_editar", args=[membro.pk]))
    assert list(resp.context["historico"]) == list(historico_de(membro))
    assert "MEMBRO" in resp.content.decode() and "DIRETOR" in resp.content.decode()


def test_link_usuarios_so_aparece_para_diretor(client, diretor, membro):
    url = reverse("web:usuarios")
    client.force_login(diretor)
    assert url in client.get(reverse("web:inicio")).content.decode()
    client.force_login(membro)
    assert url not in client.get(reverse("web:inicio")).content.decode()
