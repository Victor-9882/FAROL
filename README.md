# FAROL

**F**erramenta de **A**companhamento, **R**etenção e **O**rientação **L**ongitudinal: aplicação web de apoio à decisão para a Direção do CASD (CASDvest). Projeto da disciplina CSI-28 (ITA, 2026.2).

> ⚠️ **Repositório público.** Nunca versione planilhas reais, exportações do P+, da catraca ou do Corrija-me, nem o arquivo `.env`. Em desenvolvimento e testes use só dados sintéticos (NF017).

## Stack

Python 3.12 · Django 5.2 LTS · PostgreSQL 16 · [uv](https://docs.astral.sh/uv/) para dependências · pytest e ruff.

## Estrutura

Cada app Django corresponde a uma camada da arquitetura (Relatório Descritivo, Seção 1.3; GConfig, Seção 6):

| Diretório | Camada |
|---|---|
| `farol/` | Configuração do projeto (settings, urls) |
| `ingestao/` | Integração e Ingestão: importação de catraca, P+, Corrija-me e planilhas |
| `inteligencia/` | Inteligência: motor de indicadores e motor de regras |
| `core/` | Aplicação Core: alunos, turmas, alertas, intervenções, usuários |
| `relatorios/` | Relatórios e Notificações |
| `web/` | Apresentação |
| `tests/` | Testes automatizados e base sintética (`tests/dados_sinteticos/`) |
| `docs/` | Documentação; os relatórios da disciplina estão em `docs/relatorios/` |

As migrações ficam em `<app>/migrations/`, como é o padrão do Django, e não num `db/migrations/` central, como previa o GConfig.

## Rodar com Docker Compose (recomendado)

Sobe o mesmo ambiente em qualquer máquina: aplicação, PostgreSQL 16 e [Mailpit](https://mailpit.axllent.org/), um servidor de e-mail de teste que captura as mensagens sem entregá-las.

```bash
cp .env.example .env              # ajuste DJANGO_SECRET_KEY; o .env nunca é versionado
docker compose up --build         # aplica as migrações e sobe o servidor
```

| Serviço | Endereço |
|---|---|
| Aplicação | <http://localhost:8000/saude/> e <http://localhost:8000/admin/> |
| Mailpit (caixa de entrada de teste) | <http://localhost:8025> |
| PostgreSQL | `localhost:5432`, usuário, senha e banco conforme o `.env` |

Comandos úteis, com o ambiente no ar:

```bash
docker compose exec app python manage.py createsuperuser
docker compose exec app python manage.py sendtestemail voce@exemplo.org   # aparece no Mailpit
docker compose exec app pytest
docker compose down               # para tudo; acrescente --volumes para apagar o banco
```

O código é montado como volume, então alterações aparecem sem reconstruir a imagem. Só rode `--build` de novo quando mudar `pyproject.toml` ou `uv.lock`. No Linux, arquivos criados dentro do contêiner (por exemplo, por `makemigrations`) ficam com dono `root`. Prefira gerar migrações com o uv na própria máquina.

## Rodar sem Docker

1. Instale o uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Instale as dependências: `uv sync`
3. Defina as variáveis de ambiente, copiando o `.env.example` para `.env` (nunca versionado) ou no shell:

   | Variável | Obrigatória | Exemplo |
   |---|---|---|
   | `DJANGO_SECRET_KEY` | sim | qualquer texto longo e aleatório |
   | `DJANGO_DEBUG` | não (padrão `False`) | `True` |
   | `DJANGO_ALLOWED_HOSTS` | não (padrão `localhost,127.0.0.1`) | `localhost,127.0.0.1` |
   | `DATABASE_URL` | não (padrão `postgres://farol:farol@localhost:5432/farol`) | `postgres://farol:farol@localhost:5432/farol` |
   | `EMAIL_URL` | não (padrão: e-mails no console) | `smtp://localhost:1025` |

4. Aplique as migrações e suba o servidor:

   ```bash
   uv run python manage.py migrate
   uv run python manage.py createsuperuser
   uv run python manage.py runserver
   ```

   A aplicação fica em <http://localhost:8000/saude/> e o admin em <http://localhost:8000/admin/>.

Sem PostgreSQL instalado, dá para usar SQLite só para experimentar: `DATABASE_URL=sqlite:///db.sqlite3`. A CI sempre roda com PostgreSQL.

## Testes e estilo

```bash
uv run pytest --cov             # suíte completa; falha abaixo da meta de cobertura (fail_under)
uv run pytest -m regras         # só as regras de negócio dos alertas
uv run ruff check . && uv run ruff format --check .
```

Marque com `@pytest.mark.regras` os testes das regras RN001, RN002, RN005, RN008 e RN009, que a CI roda primeiro.

## Contribuir

O fluxo de branches, commits e PRs está em [docs/configuracao-github.md](docs/configuracao-github.md), seção 9. Resumo: uma branch curta por issue (`tipo/RFxxx-descricao`), commits em Conventional Commits citando o requisito, PR revisado por outro integrante e CI verde.
