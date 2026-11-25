# FAROL · Instalação local com banco persistente

Este guia instala o FAROL no computador da Direção. A aplicação abre no navegador em `http://127.0.0.1:8000/` e o PostgreSQL guarda os registros em um volume do Docker. O acesso é exclusivo do próprio computador. Para acesso por outras máquinas, consulte o [guia de hospedagem compartilhada](guia-hospedagem-compartilhada.md).

## 1. O que a equipe prepara antes da entrega

Use uma versão identificada do FAROL, com `manage.py`, `pyproject.toml`, `uv.lock`, `.dockerignore` e as pastas da aplicação. Inclua em `web/static/` as imagens referenciadas pelos templates da versão entregue. Conserve o número da versão junto ao pacote para conseguir reinstalá-la ou recuperar um backup.

O Compose de desenvolvimento do repositório usa o `runserver` e o Mailpit para homologação. Para a operação diária, prepare os três arquivos abaixo no pacote de instalação. O Gunicorn executa o Django com a depuração desligada, e o WhiteNoise entrega os arquivos estáticos coletados. [Servidor WSGI com Gunicorn no Django](https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/gunicorn/), [WhiteNoise no Django](https://whitenoise.readthedocs.io/en/stable/django.html)

### Dockerfile.operacao

Salve este arquivo ao lado de `manage.py`.

```dockerfile
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project \
    && uv pip install --python /opt/venv/bin/python \
        gunicorn==27.0.1 whitenoise==6.12.0

COPY . .
RUN useradd --system --uid 10001 --user-group farol \
    && mkdir -p /app/staticfiles \
    && chown farol:farol /app/staticfiles

USER farol

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && exec gunicorn farol.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120"]
```

As dependências da aplicação vêm do `uv.lock`. As duas dependências de operação estão fixadas no exemplo. A equipe pode atualizar suas versões junto com a próxima entrega e repetir a verificação da instalação.

### farol/settings_operacao_local.py

Salve este arquivo dentro da pasta que já contém `settings.py`. Ele reaproveita as configurações do FAROL e acrescenta a entrega da logo e dos demais arquivos estáticos.

```python
from .settings import *  # noqa: F403
from .settings import MIDDLEWARE as MIDDLEWARE_BASE

MIDDLEWARE = [
    MIDDLEWARE_BASE[0],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE_BASE[1:],
]
STATIC_URL = "/static/"
```

### compose.operacao.yml

Salve este arquivo ao lado de `manage.py`. O Compose publica apenas a porta da aplicação em `127.0.0.1`. O banco é acessado pelo serviço `db` na rede interna do Docker e guarda os arquivos no volume `farol-operacao-local_dados`. [Publicação de portas no Docker](https://docs.docker.com/engine/network/port-publishing/), [Volumes do Docker](https://docs.docker.com/engine/storage/volumes/)

```yaml
name: farol-operacao-local

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile.operacao
    env_file: .env.operacao
    environment:
      DJANGO_SETTINGS_MODULE: farol.settings_operacao_local
      DATABASE_URL: "postgres://farol:${POSTGRES_PASSWORD:?Defina POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-farol}"
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude/', timeout=3)"
      interval: 5s
      timeout: 5s
      retries: 20
      start_period: 20s

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: farol
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?Defina POSTGRES_PASSWORD}"
      POSTGRES_DB: "${POSTGRES_DB:-farol}"
    volumes:
      - dados:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "pg_isready", "-h", "127.0.0.1", "-U", "farol", "-d", "postgres"]
      interval: 5s
      timeout: 5s
      retries: 12

volumes:
  dados:
```

## 2. Primeira instalação no computador da Direção

1. Instale o Docker Desktop ou, no Linux, o Docker Engine com o plugin Compose. Abra o Docker e confira `docker compose version`. Tenha acesso à internet na primeira instalação para baixar as imagens e as dependências. [Instalação oficial do Docker Compose](https://docs.docker.com/compose/install/)
2. Extraia o pacote para uma pasta fixa e abra nela o terminal. No Windows, digite `powershell` na barra de endereços do Explorador de Arquivos. No macOS ou Linux, use `cd` no Terminal para entrar na pasta onde está `manage.py`.
3. Crie o arquivo `.env.operacao` como texto simples, na mesma pasta. Use o modelo abaixo e gere uma chave e uma senha próprias para a instalação. A senha do PostgreSQL deve usar caracteres hexadecimais para entrar diretamente no endereço de conexão.

   ```bash
   docker run --rm python:3.12-slim python -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(50)); print('POSTGRES_PASSWORD=' + secrets.token_hex(32))"
   ```

   Substitua as duas linhas indicadas pelos valores gerados. Guarde o arquivo em local privado. O modo HTTP está limitado à interface local indicada no Compose.

   ```dotenv
   DJANGO_SECRET_KEY=COLE_A_CHAVE_GERADA
   POSTGRES_PASSWORD=COLE_A_SENHA_HEXADECIMAL_GERADA
   POSTGRES_DB=farol
   DJANGO_DEBUG=False
   DJANGO_HTTPS=False
   DJANGO_ALLOWED_HOSTS=127.0.0.1
   SITE_URL=http://127.0.0.1:8000
   EMAIL_URL=consolemail://
   ```

4. Na primeira execução, rode os comandos a seguir. O primeiro prepara a aplicação e o banco e aplica as migrações. O segundo pede nome de usuário, e-mail e senha para criar a primeira conta com perfil **Diretor**.

   ```bash
   docker compose --env-file .env.operacao -f compose.operacao.yml up -d --build --wait
   docker compose --env-file .env.operacao -f compose.operacao.yml exec app python manage.py createsuperuser
   ```

5. Abra [a página de verificação](http://127.0.0.1:8000/saude/) e confirme `{"status": "ok"}`. Em seguida, abra [o FAROL](http://127.0.0.1:8000/), entre e confira o perfil **Diretor** no cabeçalho. A aplicação cria a estrutura do banco e as regras iniciais. Os cadastros do curso são carregados pela Direção, conforme o [manual de uso](guia-uso-final.md).

## 3. Abrir e fechar no dia a dia

Com o Docker aberto, execute o comando abaixo na pasta do FAROL.

```bash
docker compose --env-file .env.operacao -f compose.operacao.yml up -d --wait
```

Quando terminar, use **Sair** no navegador. Encerre a aplicação e o banco com o comando abaixo.

```bash
docker compose --env-file .env.operacao -f compose.operacao.yml stop
```

`stop` preserva os dados. O volume é onde o PostgreSQL mantém registros, contas e histórico. Use o mesmo nome de projeto e preserve o `.env.operacao` ao atualizar. O PostgreSQL grava a senha na primeira inicialização do volume, e trocar apenas o valor no arquivo interrompe a conexão. A opção `down --volumes` remove o volume e apaga o banco desse projeto.

Se a página não abrir, confira se o Docker está em execução. Consulte o status e os logs com os comandos abaixo. Se outro programa ocupar a porta 8000, a equipe pode trocar apenas a porta do lado esquerdo do mapeamento no Compose e ajustar `SITE_URL` e o endereço do navegador. A porta 8000 interna permanece a mesma.

```bash
docker compose --env-file .env.operacao -f compose.operacao.yml ps
docker compose --env-file .env.operacao -f compose.operacao.yml logs --tail=80 app db
```

## 4. Fazer e verificar backups

Crie a pasta `backups` na pasta do FAROL para receber as cópias. Substitua `AAAA-MM-DD` pela data do backup. Os comandos consideram o banco inicial `farol`. Se a instalação tiver adotado outro nome, use em `-d` o valor atual de `POSTGRES_DB`.

```bash
docker compose --env-file .env.operacao -f compose.operacao.yml exec -T db pg_dump -U farol -d farol -Fc -f /tmp/farol.dump
docker compose --env-file .env.operacao -f compose.operacao.yml cp db:/tmp/farol.dump backups/farol-AAAA-MM-DD.dump
```

Confira se o arquivo foi copiado. Guarde backups em um local privado e separado do disco do computador, com acesso controlado pelo CASD. Combine uma rotina periódica de backup e faça uma cópia antes de cada atualização. Guarde separadamente a configuração necessária para recuperar a instalação. [Backup do PostgreSQL](https://www.postgresql.org/docs/16/backup.html), [Cópia de arquivos pelo Docker Compose](https://docs.docker.com/reference/cli/docker/compose/cp/)

A equipe pode ensaiar a restauração em um banco novo, preservando o banco em uso. Use um nome livre para o banco de verificação e execute os comandos abaixo em ordem.

```bash
docker compose --env-file .env.operacao -f compose.operacao.yml cp backups/farol-AAAA-MM-DD.dump db:/tmp/farol-restaurar.dump
docker compose --env-file .env.operacao -f compose.operacao.yml exec -T db createdb -U farol farol_verificacao
docker compose --env-file .env.operacao -f compose.operacao.yml exec -T db pg_restore -U farol -d farol_verificacao --no-owner --no-privileges --exit-on-error /tmp/farol-restaurar.dump
docker compose --env-file .env.operacao -f compose.operacao.yml exec -T db psql -U farol -d farol_verificacao -c "SELECT count(*) FROM django_migrations"
```

Em uma recuperação real, a equipe pode instalar a versão que gerou a cópia em uma máquina nova, iniciar o serviço `db` com `up -d --wait db` e restaurar o arquivo em um banco novo como acima. Após verificar a restauração, ajuste `POSTGRES_DB` no `.env.operacao` para o banco restaurado e inicie a aplicação com `up -d --wait`. Entre com uma conta recuperada e confira alunos, intervenções e uma ficha conhecida. O procedimento mantém o banco original separado. [Restauração com pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html)

## 5. Atualizar para outra versão

1. Combine com a Direção a interrupção do uso. Pare somente `app` com `docker compose --env-file .env.operacao -f compose.operacao.yml stop app` e faça um backup enquanto `db` estiver em execução.
2. Extraia a nova versão em uma pasta própria. Preserve o `.env.operacao` e confirme que o Compose mantém o mesmo nome de projeto e de volume. Guarde a versão anterior junto ao backup.
3. Na pasta nova, execute `docker compose --env-file .env.operacao -f compose.operacao.yml up -d --build --wait`. A aplicação aplica as migrações pendentes ao iniciar.
4. Confira `/saude/`, o login e dados já existentes. Se a migração falhar, pare o serviço da aplicação, preserve o banco e peça à equipe para diagnosticar ou recuperar a versão anterior a partir do backup verificado.

## 6. E-mail de fechamento

Com a configuração acima, os e-mails aparecem no console. Se o curso optar pelo envio, a equipe configura `EMAIL_URL` e `DEFAULT_FROM_EMAIL` com o serviço institucional e testa o destinatário antes da operação. Mantenha `SITE_URL` como endereço local enquanto só a máquina da Direção acessar o sistema. Um destinatário em outro computador consegue ler a mensagem, e o endereço local abre apenas na máquina que executa o FAROL.

Para executar o fechamento manualmente, mantenha o FAROL em execução e informe o ano letivo em que está trabalhando.

```bash
docker compose --env-file .env.operacao -f compose.operacao.yml exec -T app python manage.py gerar_alertas --ano 2026
docker compose --env-file .env.operacao -f compose.operacao.yml exec -T app python manage.py notificar_ciclo
```

O segundo comando seleciona o ciclo fechado mais recente que tem resultados e registra o envio. Teste com uma conta comum ativa com e-mail cadastrado. A conta criada com `createsuperuser` fica fora dos destinatários. Se a equipe agendar a rotina no sistema operacional, programe-a para um horário em que o computador e o FAROL estejam ligados.

## 7. Conferir antes de usar dados do curso

- Entre, confirme o perfil **Diretor** e verifique o carregamento da página e dos arquivos estáticos.
- Faça o [exercício de validação com as planilhas fictícias](guia-validacao-direcao.md) em um banco de homologação separado.
- Na instalação de operação, confira que a lista de alunos está vazia antes da primeira carga. Valide com a equipe a guarda do backup e faça um ensaio de restauração.
