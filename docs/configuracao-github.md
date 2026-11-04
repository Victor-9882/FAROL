# Configuração do GitHub — FAROL

Passo a passo para colocar no ar o repositório descrito no Plano de Controle de Configuração (FAROL_GConfig, Seções 5 a 7). Responsável: gerente de configuração.

> ⚠️ **O repositório é público.** Código, issues, PRs, comentários e logs do GitHub Actions podem ser lidos por qualquer pessoa. Dados reais de alunos ficam **só** na pasta `04_Dados_Cliente` do Drive. Credenciais ficam em `.env` (local) e nos *secrets* do GitHub.

## 1. Organização e repositório

1. Crie a organização (plano Free), por exemplo `farol-casd`, e convide os quatro integrantes.
2. Em *People*, mantenha só o gerente de configuração como **Owner**.
3. Crie o repositório público `farol`, **sem** README, `.gitignore` nem licença (esses arquivos vêm deste pacote).
4. Em *Settings → Collaborators and teams*, dê permissão **Write** aos outros quatro integrantes.

## 2. Subir os arquivos iniciais

1. Troque os marcadores:
   - os `@SUBSTITUIR-<nome>` em `.github/CODEOWNERS` pelos usuários reais do GitHub;
   - o link do Drive em `.github/ISSUE_TEMPLATE/config.yml`.
2. Rode, a partir da pasta descompactada:

```bash
git init -b main
git add .
git commit -m "chore: estrutura inicial do repositório"
git remote add origin https://github.com/Victor-9882/FAROL
git push -u origin main
```

Esse é o único push direto na `main`. Depois do passo 4, tudo entra por pull request.

## 3. Labels

Rode o script com o GitHub CLI autenticado (`gh auth login`):

```bash
./scripts/criar_labels.sh ORGANIZACAO/farol
```

O script cria as labels de tipo, severidade e estado de SM. As labels padrão do GitHub (`bug`, `enhancement`…) **não** são apagadas. Elas podem ser removidas à mão em *Issues → Labels*, se a equipe preferir.

Rode o script **antes** de abrir as primeiras issues, porque os formulários só aplicam labels que já existem.

## 4. Proteção da `main` (ruleset)

Em *Settings → Rules → Rulesets → New branch ruleset*:

- **Nome:** `protecao-main`
- **Enforcement:** Active
- **Target branches:** *Include default branch*
- **Bypass list:** vazia. Ninguém, nem o owner, integra sem PR.

Regras a marcar:

- [x] **Restrict deletions**
- [x] **Require linear history**
- [x] **Require a pull request before merging**
  - Required approvals: **1**
  - [x] Dismiss stale pull request approvals when new commits are pushed
  - [x] Require conversation resolution before merging
  - [ ] Require review from Code Owners: **deixe desmarcado**. Quase todo PR mexe em `tests/`, e exigir a aprovação do Yuri em todos criaria um gargalo. O CODEOWNERS continua *pedindo* a revisão automaticamente.
  - Allowed merge methods: **Squash**
- [x] **Require status checks to pass**
  - [x] Require branches to be up to date before merging
  - Checks exigidos (aparecem na lista depois que a CI rodar uma vez):
    - `Estilo (ruff)`
    - `Migrações em banco vazio`
    - `Testes`
    - `Título em Conventional Commits`
- [x] **Block force pushes**

## 5. Outras configurações do repositório

Em *Settings → General → Pull Requests*:

- [ ] Allow merge commits
- [x] Allow squash merging, com *Default commit message* = **Pull request title**
- [ ] Allow rebase merging
- [x] Automatically delete head branches

Em *Settings → Actions → General*:

- **Workflow permissions:** *Read repository contents and packages permissions*
- **Fork pull request workflows:** *Require approval for all external contributors*

Em *Settings → Code security*:

- [x] **Secret scanning** e **Push protection**, gratuitos em repositórios públicos. Bloqueiam pushes que contenham chaves e senhas.
- [x] **Dependabot alerts** e **Dependabot security updates**

## 6. Quadro Kanban (GitHub Projects)

Na organização, *Projects → New project → Board*, com o nome `FAROL — Kanban`.

**Campo Status** (colunas do Relatório Descritivo, Seção 1.2):

1. A Fazer
2. Em Desenvolvimento (limite da coluna: 5)
3. Em Revisão
4. Concluído

**Campos personalizados (single select):**

- **Módulo:** Ingestão, Indicadores, Alertas, Intervenções/Relatórios
- **Prioridade:** Essencial, Importante, Desejável

**Visões:**

| Visão | Layout | Configuração |
|---|---|---|
| Quadro | Board | *Slice by:* Módulo |
| Por integrante | Table | *Group by:* Assignees, para conferir o WIP de cada um |
| Defeitos | Table | Filtro `label:defeito is:open`, *Group by:* Labels |
| Roteiro | Table | *Group by:* Milestone |

**Workflows do projeto** (*⋯ → Workflows*):

- *Auto-add to project*: repositório `farol`, filtro `is:issue`
- *Item added to project* → Status = A Fazer
- *Item closed* → Status = Concluído
- *Pull request merged* → Status = Concluído
- *Item reopened* → Status = A Fazer

As colunas "Em Desenvolvimento" e "Em Revisão" são movidas por quem pegou o card. As SMs só entram no quadro depois de `sm:aprovada`. Até lá, filtre com `-label:sm:em-analise -label:sm:aguardando-direcao`.

## 7. Milestones

Em *Issues → Milestones*, crie uma por versão da Tabela 2 do GConfig:

- `v0.1.0` Protótipo validado
- `v0.2.0` Ingestão
- `v0.3.0` Indicadores e Alertas
- `v0.4.0` Intervenções e Relatórios
- `v1.0.0` Entrega final validada com o cliente

## 8. Ambientes (quando houver deploy)

Em *Settings → Environments*:

- **`homologacao`**: sem revisor obrigatório. Recebe deploy a cada integração na `main`, apenas com dados sintéticos.
- **`producao`**:
  - *Required reviewers*: gerente de configuração
  - *Deployment branches and tags*: **Selected** → padrão de tag `v*`
  - *Secrets*: credenciais do banco de produção e do serviço de e-mail. Nunca no repositório.

## 9. Fluxo do dia a dia

1. Pegue um card em **A Fazer** e mova-o para **Em Desenvolvimento**, respeitando o limite de WIP.
2. Na issue, clique em *Create a branch*, com o nome `tipo/RFxxx-descricao` (ex.: `feat/RF003-importar-frequencia`). A branch fica vinculada à issue.
3. Faça commits em Conventional Commits, citando o requisito.
4. Abra o PR com título no padrão e `Closes #<issue>` na descrição. Mova o card para **Em Revisão**.
5. Peça a revisão de outro integrante (Matheus ↔ Pietro; testes → Yuri).
6. Com a CI verde e 1 aprovação, faça o **Squash and merge**. O card vai sozinho para **Concluído**.

## 10. Liberar uma versão

1. O engenheiro de testes abre uma issue **Auditoria de linha de base** e a fecha com o resultado.
2. O gerente de configuração cria a tag na `main` e a Release:

```bash
git switch main && git pull
git tag -a v0.2.0 -m "v0.2.0 — Ingestão"
git push origin v0.2.0
gh release create v0.2.0 --generate-notes --title "v0.2.0 — Ingestão"
```

3. O resultado da auditoria e a tag vão para o Registro de Configuração (IC-05).

## Pendências quando o código começar

- Criar `pyproject.toml` e `uv.lock` (`uv init`, `uv add django ...`) e o projeto Django (`manage.py` na raiz). A CI passa a rodar migrações e testes automaticamente.
- Registrar o marker `regras` no `pyproject.toml`, `[tool.pytest.ini_options] markers = ["regras: regras de negócio dos alertas"]`, e marcar os testes das RN001, RN002, RN005, RN008 e RN009.
- Definir `fail_under` em `[tool.coverage.report]`.
- Criar `.env.example`, `Dockerfile` e `docker-compose.yml`, e `config/regras_padrao.yaml` quando os limiares forem definidos com o cliente.
