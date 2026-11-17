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
