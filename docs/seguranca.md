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
