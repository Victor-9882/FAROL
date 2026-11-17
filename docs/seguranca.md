# Segurança do FAROL

## Login e admin

**Decisão (issue #49, RF001, NF013, NF014):** o FAROL tem uma única tela de login, `/entrar/`. O formulário de `/admin/login/` do Django foi desativado.

**Fluxo:**
- Anônimo em qualquer rota de `/admin/` termina em `/entrar/?next=<rota>`. As rotas do `AdminSite` passam antes por `/admin/login/`, que apenas redireciona; as views de `ModelAdmin` vão direto à tela de entrada.
- Depois do login, o `LoginView` valida o `next` (destino externo é descartado e o usuário vai ao painel) e devolve o usuário ao admin.
- `/admin/login/` nunca autentica, nem por POST (`web.acesso.entrada_do_admin`). Staff já autenticado vai ao índice do admin.
- Autenticado sem `is_staff` (Membro ou Diretor comum) recebe 403 no admin. Redirecioná-lo a `/entrar/` criaria um laço, porque a tela de entrada redireciona quem já está autenticado.
- O critério de acesso ao admin continua sendo `is_staff`; o perfil (Diretor/Membro) não entra nele.

**Por que não liberar o login do admin no middleware:** isso exigiria isentar `/admin/` do `LoginRequiredMiddleware`, enfraquecendo o "negar por padrão" (NF014): uma rota futura do admin sem `admin_view` ficaria pública. Com uma só tela, o middleware não muda e o limite de tentativas de login (issue #47) vale em um único formulário.

## Limite de tentativas

**Decisão (issue #47, RF001, NF013, NF014):** o login é limitado com o `django-axes` (9.x). Depois de 5 tentativas erradas para o mesmo nome de usuário, a entrada daquele usuário é bloqueada por 15 minutos.

**Configuração** (`farol/settings.py`; `.env.example`):
- `LOGIN_LIMITE_TENTATIVAS` (padrão 5) e `LOGIN_BLOQUEIO_MINUTOS` (padrão 15). Valor menor que 1 impede o servidor de subir (`ImproperlyConfigured`).
- Backend `AxesStandaloneBackend` antes do `ModelBackend`, `AxesMiddleware` por último. `authenticate()` sem `request` é recusado pelo backend; os testes que chamam `client.login` passam um `HttpRequest()`.
- O bloqueio devolve 429 com `web/bloqueado.html`, que não mostra o usuário digitado nem as tentativas restantes. Antes do limite, a falha mostra só o erro genérico do formulário. Usuário inexistente se comporta igual a usuário existente, para não revelar quais nomes existem.
- O resfriamento conta a partir da última falha que levou ao bloqueio e não é prorrogado por novas tentativas durante ele. Um login bem-sucedido zera as falhas.

**Por que só o nome de usuário na chave:** o proxy do deploy ainda não existe. Com o IP na chave, um `X-Forwarded-For` forjado contornaria o limite; com o IP sozinho, atrás de proxy ou NAT, cinco erros bloqueariam todos. O custo aceito é que quem sabe o nome de usuário do Diretor pode mantê-lo bloqueado, o que o resfriamento fixo e o desbloqueio abaixo limitam. O aviso `axes.W006` (que pede o IP na chave) está silenciado em `SILENCED_SYSTEM_CHECKS` por essa escolha. O IP gravado é o `REMOTE_ADDR` e serve só de registro. Se o IP entrar na chave, será preciso `django-axes[ipware]`, `AXES_IPWARE_PROXY_COUNT` e `AXES_IPWARE_META_PRECEDENCE_ORDER` do proxy real. O contador fica no banco (`AxesDatabaseHandler`), não no cache, porque o cache local é por processo e não vale com mais de um worker.

**Desbloquear:**
- Espera: o bloqueio expira sozinho.
- Admin (só superusuário): excluir o registro em "Tentativas de acesso" (`AccessAttempt`).
- Linha de comando: `python manage.py axes_reset_username <usuario>`. `axes_reset` apaga todas as tentativas e bloqueios.

**LGPD e auditoria:**
- O `AccessAttempt` guarda o nome de usuário digitado, o IP e o navegador das tentativas falhas. O campo de usuário pode receber, por engano, uma senha digitada no campo errado; por isso a tabela só é visível a superusuário. Nenhuma senha nem token CSRF vai para o banco ou para o log (teste em `tests/test_bloqueio_login.py`).
- O registro de acessos bem-sucedidos (`AccessLog`) está desligado (`AXES_DISABLE_ACCESS_LOG`), para não guardar IP e navegador de quem entra normalmente.
- As tabelas do axes são estado operacional, com exclusão física, e ficam fora da NF007. Não usam `RegistroAlteracao` (NF009): uma tentativa bloqueada não tem autor. O rastro fica no `AccessAttempt`, no log `axes` e, no desbloqueio pelo admin, no `LogEntry`.

## Sessão, cookies e HTTPS

Decisão da issue #48 (RF001, NF013, NF014). As opções saem de `farol/seguranca.py` (`opcoes_de_seguranca`) e entram no `settings.py`.

**Modo HTTPS.** `DJANGO_HTTPS` liga ou desliga, de uma vez, cookies seguros, redirecionamento para HTTPS e HSTS. Sem a variável, vale `not DJANGO_DEBUG`: com `DJANGO_DEBUG=False` (o padrão) o site exige HTTPS. Para rodar localmente sem HTTPS, use `DJANGO_DEBUG=True` ou `DJANGO_HTTPS=False`. Um `.env` antigo com `DJANGO_DEBUG=False` e sem `DJANGO_HTTPS` passa a redirecionar para HTTPS: atualize-o. Os testes forçam `SECURE_SSL_REDIRECT=False` (fixture `_suite_por_http`) e os do modo HTTPS o ligam por conta própria.

| Variável | Padrão | Efeito |
|---|---|---|
| `DJANGO_HTTPS` | `not DJANGO_DEBUG` | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT` e HSTS |
| `DJANGO_SESSION_COOKIE_AGE` | `28800` (8 horas) | Duração absoluta da sessão, em segundos; precisa ser maior que zero |
| `DJANGO_SESSION_EXPIRE_AT_BROWSER_CLOSE` | `True` | A sessão também termina ao fechar o navegador |
| `DJANGO_SECURE_HSTS_SECONDS` | `2592000` (30 dias) | Só vale com HTTPS ligado; sem HTTPS, HSTS fica em 0 |
| `DJANGO_SECURE_PROXY_SSL_HEADER` | `False` | Se `True`, confia em `X-Forwarded-Proto: https` do proxy |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | vazio | Origens com esquema, separadas por vírgula (`https://farol.exemplo.org`) |

**Decisões:**
- **Fechar o navegador encerra a sessão.** O sistema tem dados nominais e pode ser aberto em computador compartilhado. O prazo de 8 horas no servidor continua valendo, porque navegadores que restauram a sessão e celulares não "fecham". Custo: entrar de novo a cada abertura do navegador.
- **8 horas absolutas, sem `SESSION_SAVE_EVERY_REQUEST`:** cobre um turno de trabalho e evita uma escrita no banco por requisição.
- **`HttpOnly` e `SameSite=Lax`** ficam nos padrões do Django.
- **HSTS de 30 dias, sem `includeSubDomains` nem `preload`:** o domínio do deploy não está definido e o preload é compromisso de longo prazo.
- **`SECURE_PROXY_SSL_HEADER` desligado por padrão:** confiar em `X-Forwarded-Proto` sem um proxy que o sobrescreva permite forjar "conexão segura". Atrás de um proxy que termina o TLS, sem `DJANGO_SECURE_PROXY_SSL_HEADER=True`, o redirecionamento entra em laço.
- **`/saude/` é isenta do redirecionamento**, para verificações de saúde por HTTP interno; a rota não expõe dado.

**Exceções do `check --deploy`** (`SILENCED_SYSTEM_CHECKS`): `security.W005` (HSTS com `includeSubDomains`) e `security.W021` (HSTS com `preload`), pelos motivos acima. As demais, em modo de produção e com `DJANGO_SECRET_KEY` forte, passam sem aviso (teste `test_check_deploy_sem_avisos_em_modo_producao`).

**Passo a passo de deploy:**
1. Gere a chave: `python -c "import secrets; print(secrets.token_urlsafe(64))"` e guarde em `DJANGO_SECRET_KEY`, fora do repositório.
2. Defina `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS` com o domínio e `DJANGO_CSRF_TRUSTED_ORIGINS` com a origem `https://`.
3. Se houver proxy que termina o TLS e sobrescreve `X-Forwarded-Proto`, defina `DJANGO_SECURE_PROXY_SSL_HEADER=True`.
4. Rode `DJANGO_DEBUG=False python manage.py check --deploy`: não deve haver avisos.
5. A imagem do `Dockerfile` usa `runserver` (desenvolvimento); o servidor de produção está fora do escopo desta issue.
