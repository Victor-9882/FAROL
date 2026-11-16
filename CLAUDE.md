# FAROL: instruções para o Claude Code

Aplicação web de apoio à decisão para a Direção do CASD (CASDvest). Projeto da disciplina CSI-28 (ITA, 2026.2). Escreva código, commits, PRs e documentação em **português do Brasil**.

## Leia antes de mexer no domínio

- [docs/dominio-casd.md](docs/dominio-casd.md): fatos confirmados sobre o CASD. Inclui o formato da matrícula, quem vê dados nominais, como o calendário funciona, de onde vêm os temas de redação e os cuidados com planilhas reais.
- [docs/modelo-de-dados.md](docs/modelo-de-dados.md): modelos, garantias (NF007, NF008, NF009) e diferenças em relação ao DER.
- [FAROL_Contexto.md](FAROL_Contexto.md): requisitos (RF, RN, NF), equipe e processo. É de 04/11/2026: o que ele diz sobre o estado do código ("ainda sem código", "stack não definida") está desatualizado.
- [docs/configuracao-github.md](docs/configuracao-github.md): fluxo de branches, commits e PRs (seção 9).

## Regras que não se negociam

- **Repositório público.** Nunca versione nem cole em issue, PR ou comentário: planilhas ou exportações reais (catraca, P+, Corrija-me, cadastro, calendário), o `.env`, nomes de alunos, professores, palestrantes ou membros da gestão. Use só a base sintética de `tests/dados_sinteticos/` (NF017).
- **Requisito não se decide no PR.** Se uma mudança altera um RF, RN ou NF (por exemplo, quem vê qual dado), ela precisa de uma Solicitação de Mudança: issue com o modelo "Solicitação de Mudança (SM)". Cite a SM no código e na documentação. Nunca justifique com "por decisão do usuário".
- **Dados nominais:** a regra vale como está em `docs/dominio-casd.md`, seção 3 (RN013 com a SM #58). Rota com dado nominal ou com escrita usa `@diretor_required` (`web/acesso.py`). Importar, cadastrar e editar é só do Diretor.
- **Sem exclusão física (NF007):** modelos de histórico herdam de `core.historico.HistoricoPreservado`. Desative em vez de excluir.
- **Auditoria (NF009):** toda alteração feita por tela ou importação grava `RegistroAlteracao` com `core.auditoria.registrar_alteracoes`. Nunca guarde senha, hash, token nem conteúdo de arquivo.
- **Importações:** idempotentes (NF008); leem com `ingestao.leitura.ler_tabela` (limites de tamanho, linhas e colunas; o de linhas vem de `IMPORTACAO_LIMITE_LINHAS`). Use `ingestao.base` (`ResumoImportacao`, `triar`, `transacao_de_importacao`, `linha_isolada`) e, nas telas, `web.importacao.executar_importacao`: a conferência sem gravar é obrigatória e só o token dela (`ingestao.confirmacao`, sem estado no servidor) permite gravar. Linha sem aluno correspondente vira `PendenciaImportacao` (`ingestao.pendencias`): nunca a descarte nem adivinhe o aluno pelo nome (RN003). Mensagens de erro nunca incluem conteúdo de células.
- **Planilhas reais:** os layouts da grade de presença, do P+ e do Corrija-me estão em `ingestao/planilhas_casd.py` e em `docs/dominio-casd.md`, seção 6. Teste com as réplicas sintéticas de `tests/dados_sinteticos/pequena/2026/planilhas/`; os arquivos reais ficam só no Drive.
- **Matrícula:** valide com `ingestao.cadastro.validar_matricula`. Uma matrícula de outro ano letivo nunca muda um aluno de turma.
- **Dia letivo (RN005):** para saber se um dia é letivo, use sempre `core.calendario.eh_dia_letivo` e `dias_letivos`, na hora do cálculo. Não deduza isso consultando `DiaCalendario`: ele guarda só as exceções aos períodos letivos.

## Ambiente e comandos

Python 3.12, Django 5.2 LTS, PostgreSQL 16, dependências com `uv`.

```bash
docker compose up -d db                      # PostgreSQL local (os testes precisam de banco)
uv run pytest --cov                          # suíte completa; falha abaixo da meta de cobertura
uv run pytest -m regras                      # regras de negócio dos alertas, que a CI roda primeiro
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
```

- Sem o `uv` instalado, use `.venv/bin/pytest`, `.venv/bin/ruff` e `.venv/bin/python`.
- Sem banco no ar, `DATABASE_URL=sqlite:///:memory:` serve para uma checagem rápida, mas a CI usa PostgreSQL.
- Dependência nova: atualize o `uv.lock` no mesmo commit, porque a CI usa `uv sync --locked`.
- Marque com `@pytest.mark.regras` os testes de RN001, RN002, RN005, RN008 e RN009.

## Fluxo de trabalho

- **Uma branch curta por issue:** `tipo/RFxxx-descricao` (por exemplo, `feat/RF003-importar-frequencia`).
- **Commits e título do PR em Conventional Commits, citando o requisito:** `feat(ingestao): importa frequência da catraca (RF003)`. Tipos: feat, fix, docs, test, refactor, perf, build, ci, chore, revert.
- **PR:** use o modelo do repositório, com `Closes #<issue>`. Coloque label e marco (`v0.2.0` Ingestão, `v0.3.0` Indicadores e Alertas, `v0.4.0` Intervenções e Relatórios, `v1.0.0` entrega final).
- **Merge:** revisão de outro integrante, CI verde e **Squash and merge**.
- **Pendências encontradas em revisão** viram issue: `defeito`, com label de severidade, ou `tarefa`.
