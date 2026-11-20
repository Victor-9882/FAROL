# FAROL · Guia de hospedagem compartilhada

Este roteiro instala o FAROL para uso contínuo da equipe em um endereço como `https://farol.exemplo.org/`. Ele usa uma conta Linux com cPanel, Python 3.12, Passenger para executar o Django via WSGI e PostgreSQL para guardar os dados. Os comandos do servidor rodam como usuário da própria conta, pelo Terminal do cPanel ou por SSH. Para operar o FAROL em um único computador, siga o [guia de instalação local](guia-instalacao-local.md).

## 1. Confirmar os recursos da hospedagem

Confirme com o provedor antes de contratar ou de cadastrar dados reais.

| Recurso | O que confirmar |
|---|---|
| Python e aplicação web | **Setup Python App** do CloudLinux com Python 3.12 e Passenger, ou execução WSGI equivalente com acesso ao ambiente virtual correto. Confirme instalação por `pip`, acesso aos logs e como parar e reiniciar a aplicação. [CloudLinux Python Selector](https://docs.cloudlinux.com/cloudlinuxos/cloudlinux_os_components/#python-selector) |
| Banco | PostgreSQL 16, usado pelo projeto, ou outra versão compatível com Django 5.2, ainda mantida pelo PostgreSQL e validada antes da implantação. Se for externo, confirme a saída de rede para a porta do banco, acesso restrito ao servidor da aplicação e conexão TLS com verificação do certificado. [Bancos suportados pelo Django](https://docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes) · [Versões mantidas do PostgreSQL](https://www.postgresql.org/support/versioning/) |
| Domínio e arquivos públicos | Subdomínio próprio com certificado HTTPS renovável, raiz pública separada do código e publicação de `/static/` pelo servidor web. Se houver proxy, confirme como o Passenger recebe o esquema da conexão original. [Domínios no cPanel](https://docs.cpanel.net/cpanel/domains/domains/) |
| Operação | SSH ou Terminal, transferência por SFTP ou pelo gerenciador do painel via HTTPS, espaço para os pacotes e logs, procedimento de backup e restauração do PostgreSQL e limites de CPU, memória, conexões e upload de planilhas. Para e-mails automáticos, confirme também cron e saída para SMTP. [Cron no cPanel](https://docs.cpanel.net/cpanel/advanced/cron-jobs/) |

O cPanel oferece esses recursos conforme o plano e a configuração do provedor. Em um plano que só oferece PHP e MySQL, a instalação do FAROL exige outro ambiente.

## 2. Preparar o subdomínio

1. Em **Domains** no cPanel, crie `farol.exemplo.org` com diretório público próprio. Confirme o caminho em **Document Root**. O exemplo usa `/home/CONTA/public_html/farol` para arquivos públicos e `/home/CONTA/farol-app` para o código. Use o caminho indicado pelo seu painel.
2. Na zona DNS do domínio, aponte o subdomínio para o destino informado pelo provedor. Quando o DNS resolver, emita o certificado para esse subdomínio com AutoSSL, se disponível, ou siga o procedimento do provedor. Verifique se o certificado cobre o endereço e se a renovação está configurada. [Certificados no cPanel](https://docs.cpanel.net/cpanel/security/ssl-tls/)
3. Reserve a raiz do subdomínio, `/`, para o FAROL. Mantenha o diretório de código, o ambiente virtual, as credenciais e os backups fora da raiz pública de todos os domínios da conta.

## 3. Preparar e transferir o código

No computador, abra um terminal Bash na cópia Git do FAROL e instale o uv, se necessário. Troque `REF_APROVADA` pela tag ou pelo hash do commit que a equipe aprovou e `farol-01` por um identificador da versão, com letras, números e hífens. O pacote contém os arquivos de execução do commit e as dependências de produção exportadas do `uv.lock` desse mesmo commit. Confirme que a versão aprovada inclui em `web/static/` os logotipos e demais arquivos visuais usados pelas telas. O `git archive` inclui apenas arquivos registrados naquele commit. [Instalação do uv](https://docs.astral.sh/uv/getting-started/installation/) · [Exportação de dependências do uv](https://docs.astral.sh/uv/concepts/projects/export/)

```bash
(
  set -euo pipefail
  VERSAO=REF_APROVADA
  PACOTE="$PWD/farol-01.tar.gz"
  PREPARO=$(mktemp -d)
  trap 'rm -rf -- "$PREPARO"' EXIT
  git archive "$VERSAO" README.md pyproject.toml uv.lock manage.py \
    config core farol ingestao inteligencia relatorios web | tar -xf - -C "$PREPARO"
  cd "$PREPARO"
  uv export --locked --no-dev --no-emit-project --format requirements.txt \
    --output-file requirements.txt
  tar -czf "$PACOTE" .
)
```

Envie apenas `farol-01.tar.gz` para a pasta privada `farol-pacotes` na conta do servidor. A configuração de produção será criada no servidor. Mantenha o `.env` local, o banco de testes e as planilhas fictícias no ambiente de teste.

No Terminal do servidor, ajuste `WEBROOT` para o **Document Root** e `VERSAO` para o nome do arquivo enviado sem `.tar.gz`. Guarde esses caminhos para reutilizar em outras sessões.

```bash
APP="$HOME/farol-app"
WEBROOT="$HOME/public_html/farol"
VERSAO=farol-01
RELEASE="$APP/versoes/$VERSAO"
mkdir -p "$APP/versoes"
mkdir "$RELEASE" &&
  tar -xzf "$HOME/farol-pacotes/$VERSAO.tar.gz" -C "$RELEASE"
```

## 4. Configurar o ambiente Python e o Passenger

Em **Software → Setup Python App → Create Application**, preencha os campos abaixo. O painel pode criar um arquivo de entrada de exemplo. [Registro no Python Selector do cPanel](https://support.cpanel.net/hc/en-us/articles/360057849753-How-to-register-an-application-with-Python-Selector)

| Campo | Valor |
|---|---|
| Python version | `3.12` |
| Application root | `farol-app`, relativo à pasta da conta |
| Application URL | `farol.exemplo.org` na raiz, com caminho vazio ou `/` conforme o painel |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |
| Passenger log file, se disponível | Um arquivo privado como `/home/CONTA/farol-app/passenger.log` |

**Quando o provedor oferece Application Manager.** Registre o mesmo subdomínio e a raiz, com **Application Path** `farol-app` e ambiente **Production**. Confirme com o provedor qual executável Python 3.12 usar para criar o ambiente virtual com `python3.12 -m venv "$HOME/farol-venv"` e peça que associe o Passenger a `/home/CONTA/farol-venv/bin/python` via `PassengerPython` ou pelo mecanismo do painel. Use esse ambiente também para os próximos comandos. [Application Manager do cPanel](https://docs.cpanel.net/cpanel/software/application-manager/) · [Configuração do interpretador no Passenger](https://www.phusionpassenger.com/docs/references/config_reference/apache/#passengerpython)

Crie ou substitua `$APP/passenger_wsgi.py` com o conteúdo abaixo. Ele delega ao ponto de entrada que já existe em `farol/wsgi.py` na versão ativa.

```python
import sys
from importlib import import_module
from pathlib import Path

release = Path(__file__).resolve().parent / "atual"
sys.path.insert(0, str(release.resolve()))
application = import_module("farol.wsgi").application
```

Copie e execute a linha de ativação do ambiente virtual exibida em **Setup Python App**. Na alternativa com Application Manager, execute `source "$HOME/farol-venv/bin/activate"`. Confira que o primeiro comando mostra **Python 3.12.x** e instale a lista fixada da versão. Os hashes exportados permitem ao `pip` verificar os arquivos dos pacotes.

```bash
python --version
command -v python
python -m pip install --require-hashes -r "$RELEASE/requirements.txt"
python -m pip check
```

Anote o caminho absoluto de `python` para tarefas agendadas. Em caso de falha ao instalar `psycopg-binary`, confirme com o provedor a disponibilidade de um pacote para a arquitetura e o Python da hospedagem.

## 5. Criar o banco e configurar o ambiente de produção

Se a hospedagem oferece PostgreSQL, abra **PostgreSQL Database Wizard**, crie um banco exclusivo para o FAROL e associe a ele um usuário próprio com senha forte. Anote o host, a porta, o nome do banco e o usuário completos, inclusive o prefixo aplicado pelo painel. O usuário da aplicação precisa conectar-se ao banco e criar tabelas e outros objetos no esquema usado pelas migrações. Se usar PostgreSQL externo, crie o banco e o usuário no painel desse serviço e confirme os parâmetros de rede e TLS. [Assistente PostgreSQL no cPanel](https://docs.cpanel.net/cpanel/databases/postgresql-database-wizard/)

Na primeira instalação, gere a chave Django direto no arquivo privado. A condição abaixo preserva um arquivo preexistente.

```bash
(
  umask 077
  if [ ! -e "$APP/.env" ]; then
    python -c 'import secrets; print("DJANGO_SECRET_KEY=" + secrets.token_urlsafe(64))' \
      > "$APP/.env"
  fi
)
chmod 600 "$APP/.env"
```

Edite `$APP/.env` em um editor no servidor. Preserve a linha da chave e acrescente estas linhas com os valores da instalação. Use percent-encoding para caracteres reservados no usuário e na senha da URL, como `@` → `%40` e `#` → `%23`.

```dotenv
DJANGO_DEBUG=False
DJANGO_HTTPS=True
DJANGO_ALLOWED_HOSTS=farol.exemplo.org
DJANGO_CSRF_TRUSTED_ORIGINS=https://farol.exemplo.org
DJANGO_SECURE_PROXY_SSL_HEADER=False
DATABASE_URL=postgresql://USUARIO:SENHA_CODIFICADA@HOST:5432/BANCO
SITE_URL=https://farol.exemplo.org
```

- Para banco remoto, use `?sslmode=verify-full` na URL e siga as instruções do serviço para fornecer o certificado da autoridade certificadora. Se necessário, acrescente `&sslrootcert=/home/CONTA/certificados/ca.pem` com o caminho do arquivo no seu servidor. Use o hostname que consta no certificado. [TLS no cliente PostgreSQL](https://www.postgresql.org/docs/16/libpq-ssl.html)
- Mantenha `DJANGO_SECURE_PROXY_SSL_HEADER=False` quando o servidor já sinaliza HTTPS diretamente ao WSGI. Defina `True` somente se o provedor confirmar que o proxy encerra o TLS, remove o `X-Forwarded-Proto` enviado pelo visitante e informa o protocolo original nesse cabeçalho. Se HTTPS redirecionar em laço, confirme esse comportamento com o provedor. [Configuração de proxy no Django](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header) · [Segurança do FAROL](seguranca.md#sessão-cookies-e-https)
- Use o `.env` como fonte de configuração deste roteiro. O FAROL dá prioridade às variáveis que já existem no processo. Se o painel ou o shell já definiu uma dessas variáveis, alinhe seu valor antes de rodar comandos ou reiniciar o serviço.

Aponte a versão para a configuração da conta. Se houver uma transferência de base aprovada, siga a [seção sobre restauração](#8-guardar-e-restaurar-cópias-do-banco) antes de executar as primeiras migrações. Em uma instalação nova, use o banco vazio criado pelo painel.

```bash
ln -s "$APP/.env" "$RELEASE/.env"
cd "$RELEASE"
python manage.py check --deploy
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Em um banco novo, crie a primeira conta técnica com `python manage.py createsuperuser`. O FAROL atribui a ela o perfil **Diretor**. Use essa conta para criar as contas individuais da equipe em **Usuários**. A rotina da Direção usa contas individuais com o perfil adequado. [Lista de implantação do Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) · [Guia de uso do FAROL](guia-uso-final.md)

## 6. Publicar e verificar

Confirme que `$WEBROOT/static` será dedicado ao FAROL. Publique somente o conteúdo gerado por `collectstatic` nesse diretório. A opção `--delete` remove arquivos estáticos de versões anteriores apenas no destino indicado. Se o plano não tiver `rsync`, use o gerenciador de arquivos para substituir o conteúdo desse diretório pelos arquivos coletados. Preserve as configurações do Passenger na raiz pública. Se a hospedagem interceptar `/static/` no WSGI, peça ao provedor que configure essa rota no servidor web. [Arquivos estáticos em produção no Django](https://docs.djangoproject.com/en/5.2/howto/static-files/deployment/)

```bash
test -d "$RELEASE/staticfiles/admin" &&
  mkdir -p "$WEBROOT/static" &&
  rsync -rpt --delete --chmod=D755,F644 "$RELEASE/staticfiles/" "$WEBROOT/static/"
```

Após a publicação dos estáticos, ative a versão. No primeiro acesso o Passenger carrega o WSGI. Se já houver um processo de exemplo, reinicie no painel. Com Passenger, também é possível sinalizar o reinício pelo arquivo `tmp/restart.txt` na raiz da aplicação. [Reinício do Passenger no cPanel](https://support.cpanel.net/hc/en-us/articles/1500002443862-How-to-restart-an-application-that-s-using-cPanel-s-Application-Manager)

```bash
ln -s "$RELEASE" "$APP/atual"
mkdir -p "$APP/tmp"
touch "$APP/tmp/restart.txt"
```

Faça as verificações a partir de um navegador e de um terminal. Troque o domínio do exemplo pelo subdomínio cadastrado.

```bash
curl -fsS https://farol.exemplo.org/saude/
curl -fsSI https://farol.exemplo.org/static/admin/css/base.css
curl -sSI http://farol.exemplo.org/entrar/
```

1. Confira `{"status": "ok"}` em `/saude/`. Essa rota confirma que o FAROL está rodando e alcança o banco. O CSS deve responder **200** e a entrada em HTTP deve redirecionar para HTTPS. Para redirecionar também os arquivos públicos em HTTP, ative o redirecionamento do domínio no painel se disponível ou solicite a configuração ao provedor.
2. Abra `/entrar/` em HTTPS. Confira o visual, entre com a primeira conta, verifique o painel e saia. Confira em janela privativa que o painel pede login e que uma conta de Membro recebe acesso negado ao abrir uma rota reservada à Direção.
3. Confirme que arquivos como `/.env` e `/manage.py` recebem **403** ou **404** e que nenhum diretório público lista arquivos. Se houver erro **500** ou **503**, consulte o log privado indicado pelo painel. Em caso de falha de conexão com o banco, confira o host, as credenciais, as permissões e o acesso de rede. Em caso de **404** nos estáticos, confira o **Document Root** e o mapeamento de `/static/`.
4. Para conferir importação, perfis e indicadores de ponta a ponta, execute o [roteiro de validação da Direção](guia-validacao-direcao.md) em ambiente separado, com banco próprio e dados fictícios. Na instância institucional, carregue os dados aprovados na ordem descrita no [guia de uso do FAROL](guia-uso-final.md).

## 7. Habilitar e-mail de fechamento e agendamento

Se a Direção for usar o e-mail de fechamento, configure o SMTP institucional no `.env`. O exemplo usa STARTTLS na porta 587. Se o servidor de e-mail exigir TLS implícito, use `smtp+ssl://` e a porta informada pelo serviço, normalmente 465. Codifique caracteres reservados no usuário e na senha. O valor de `SITE_URL` deve apontar para o endereço HTTPS do FAROL. [URLs de e-mail no django-environ](https://django-environ.readthedocs.io/en/latest/types.html#environ-env-email-url)

```dotenv
EMAIL_URL=smtp+tls://USUARIO_CODIFICADO:SENHA_CODIFICADA@smtp.exemplo.org:587
DEFAULT_FROM_EMAIL=FAROL <farol@exemplo.org>
```

Na versão ativa, com o ambiente Python configurado, execute `python manage.py sendtestemail voce@exemplo.org` com um endereço autorizado. Confirme a entrega e reinicie o Passenger depois de mudar o `.env`. O FAROL usa, por padrão, um backend que escreve a mensagem no console. Habilite o comando de fechamento depois de confirmar a entrega real, pois uma execução bem-sucedida registra o ciclo como notificado.

Em **Cron Jobs**, configure uma execução diária em horário de pouco uso, por exemplo, minuto **30** e hora **6**, com dia, mês e dia da semana em `*`. Confira o fuso horário do agendador e ajuste os caminhos absolutos da conta e do executável Python. O comando do exemplo requer `flock` em `/usr/bin/flock`. Se o caminho for outro, consulte `command -v flock`. Em um servidor sem `flock`, mantenha um único agendamento e evite rodar os comandos manualmente enquanto a rotina estiver executando. [Configuração do cron no cPanel](https://docs.cpanel.net/cpanel/advanced/cron-jobs/)

```bash
/usr/bin/flock -n /home/CONTA/farol-app/rotina.lock /bin/sh -c 'cd /home/CONTA/farol-app/atual && /home/CONTA/virtualenv/farol-app/3.12/bin/python manage.py gerar_alertas && /home/CONTA/virtualenv/farol-app/3.12/bin/python manage.py notificar_ciclo' >> /home/CONTA/farol-app/rotina.log 2>&1
```

Confira o log após a primeira execução e acompanhe o espaço usado pelos logs. A rotina gera os alertas do ano atual e depois procura o ciclo encerrado mais recente com resultados, enviando o resumo agregado às contas comuns ativas com e-mail. Para recalcular outro ano, informe `--ano AAAA` em `gerar_alertas`. Evite duplicar o agendamento ou usar `--reenviar` na rotina. Sem o serviço de e-mail, você pode agendar somente `gerar_alertas`.

## 8. Guardar e restaurar cópias do banco

Combine com a Direção quem opera a instância, o intervalo de backup, a retenção e a forma de recuperar o serviço. Guarde cópias criptografadas e com acesso restrito fora da hospedagem. Preserve também a versão instalada, os parâmetros operacionais e as credenciais em armazenamento separado e protegido. Teste a restauração em um banco isolado antes de depender das cópias. Confirme o procedimento do PostgreSQL diretamente com o provedor quando o banco ou o backup forem gerenciados por ele.

Se a conta disponibilizar `pg_dump` e `pg_restore`, use clientes de versão compatível com o servidor. O exemplo cria um backup em formato customizado e lista seu conteúdo. Use os dados de conexão reais e digite a senha quando solicitada. Para banco externo, configure também `PGSSLMODE=verify-full` e, quando necessário, `PGSSLROOTCERT` no terminal conforme o serviço. [pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html) · [pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html)

```bash
umask 077
install -d -m 700 "$HOME/farol-backups"
ARQUIVO="$HOME/farol-backups/farol-$(date +%Y%m%d-%H%M%S).dump"
pg_dump --host HOST --port 5432 --username USUARIO --dbname BANCO --password \
  --format=custom --file "$ARQUIVO" &&
  pg_restore --list "$ARQUIVO"
```

Para restaurar, crie um **outro banco vazio** com permissões adequadas. Use o arquivo escolhido como `ARQUIVO` e os dados do destino no comando. A restauração em uma transação evita aplicar apenas parte da cópia em caso de erro. Aponte uma instância de verificação para esse banco, com o cron de produção desligado, e confira o acesso e os registros esperados antes de mudar a configuração da instância principal.

```bash
pg_restore --host HOST --port 5432 --username USUARIO --dbname BANCO_RESTAURADO \
  --password --no-owner --no-privileges --single-transaction "$ARQUIVO"
```

Se houver uma base PostgreSQL local de trabalho já aprovada para uso institucional, pare as gravações na origem e faça a transferência como restauração controlada antes da abertura do serviço. Use `pg_dump` na origem, transporte a cópia criptografada por canal privado como SFTP e restaure no banco vazio do servidor. No ambiente de trabalho do [guia de instalação local](guia-instalacao-local.md), o comando abaixo gera o mesmo formato a partir do serviço `db`. Execute em Bash na pasta do projeto com o banco em funcionamento e guarde o resultado em local privado até a transferência. Em uma instalação nova, prefira o banco vazio e a carga dos dados aprovados pela interface.

```bash
umask 077
ARQUIVO_LOCAL=$(mktemp "$HOME/farol-transferencia.XXXXXXXX")
docker compose --env-file .env.operacao -f compose.operacao.yml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$ARQUIVO_LOCAL" &&
  printf '%s\n' "$ARQUIVO_LOCAL"
```

Registre a versão e a data da cópia. Depois da restauração, aplique as migrações da versão que vai entrar em uso, confira os dados e cuide das cópias temporárias conforme a retenção definida. A migração usa a configuração de produção criada na hospedagem. Caso a instalação local use SQLite, prepare a carga pelos arquivos de origem ou valide uma migração específica dos dados antes da implantação.

## 9. Atualizar preservando os dados

1. Gere e transfira o pacote da nova versão, com outro identificador. Extraia-o em um novo diretório sob `$APP/versoes` como na seção 3. Guarde a versão ativa, consultando `readlink "$APP/atual"`, e teste a nova versão em uma instância com banco separado.
2. Avise a equipe da manutenção. Pause o cron e use o mecanismo do provedor para restringir o site à pessoa responsável pela implantação durante a troca. Faça uma cópia verificada do banco após interromper as gravações. Guarde a configuração em vigor de forma segura.
3. Com `RELEASE` apontando para a **nova** pasta, vincule o `.env` existente como na seção 5. Ative o ambiente Python da aplicação, instale as dependências da nova versão, rode `pip check` e `check --deploy`, revise `python manage.py migrate --plan` e aplique as migrações. Rode `collectstatic` e publique a pasta coletada como na seção 6.
4. Troque o link que o WSGI usa e reinicie. Faça as verificações da seção 6 antes de retomar o acesso e o cron. Preserve o PostgreSQL, as configurações privadas e a versão anterior até concluir a validação.

```bash
ln -sfn "$RELEASE" "$APP/atual.proximo" &&
  mv -Tf "$APP/atual.proximo" "$APP/atual" &&
  touch "$APP/tmp/restart.txt"
```

Se precisar voltar ainda durante a manutenção, reinstale as dependências da versão anterior, republique seus estáticos e reaponte o link. Se as migrações tornarem o banco incompatível com a versão anterior, restaure a cópia pré-atualização em outro banco e aponte a configuração para ele antes do reinício. Depois que a equipe voltar a gravar, preserve uma cópia do estado atual e avalie as alterações com a equipe antes de usar um backup mais antigo. Isso evita perder lançamentos feitos depois do backup.
