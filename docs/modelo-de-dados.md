# Modelo de dados

Implementação física do Diagrama de Classes e do DER do Relatório Descritivo (Seções 1.4 e 1.5). Os modelos ficam em `core/models.py` e `inteligencia/models.py`.

| Modelo | Tabela do DER | Observações |
|---|---|---|
| `core.Usuario` | Usuário | Perfil Diretor ou Membro; padrão Membro (RN013) |
| `core.Turma` | Turma | Única por nome e ano letivo |
| `core.Aluno` | Aluno | Matrícula é a chave primária (RN003); `turma` é a turma atual |
| `core.HistoricoTurma` | **nova** | Períodos do aluno em cada turma (RN011) |
| `core.PeriodoLetivo` | **nova** | Período de aulas (`inicio`, `fim`, `descricao`); as férias ficam entre dois períodos (RN005) |
| `core.DiaCalendario` | **nova** | Só exceções ao período: feriado ou emenda (não letivo) e sábado com aula (letivo), com descrição (RN005) |
| `core.CicloCalendario` | Ciclo | Duas semanas entre simulados (RN006); `data_simulado` dentro do ciclo |
| `core.TemaRedacao` | **nova** | Tema semanal, chave na terça-feira (RN007) |
| `core.RegistroFrequencia` | Frequência | Único por aluno e dia (NF008) |
| `core.ResultadoSimulado` | Simulado | Único por aluno, ciclo e área; campo `presente` (RN009) |
| `core.ResultadoRedacao` | Redação | Único por aluno e tema; competências c1 a c5 (0 a 200) |
| `core.Alerta` | Alerta | Motivo obrigatório (NF004); guarda a regra e o ciclo que o geraram |
| `core.Intervencao` | Intervenção | Ligada ao aluno e, opcionalmente, ao alerta (RF019) |
| `core.RegistroAlteracao` | **nova** | Auditoria: autor, data, campo, valor anterior e novo (NF009); reutilizada por RF008 e RF018 |
| `core.RegistroImportacao` | **nova** | Trilha de uploads: quem importou, quando e o resumo (NF007, NF009) |
| `core.PendenciaImportacao` | **nova** | Linha importada sem aluno correspondente, à espera de associação manual (RN003, NF006) |
| `inteligencia.RegraAlerta` | (só no Diagrama de Classes) | Uma regra ativa por tipo; limiares no banco (RF018) |

## Garantias

- **Sem exclusão física (NF007):** todos os modelos acima, menos `Usuario`, herdam de `core.historico.HistoricoPreservado`. `delete()` gera `ExclusaoProibidaError`, tanto no objeto quanto em querysets. As chaves estrangeiras usam `PROTECT`. Um usuário de gestão anterior é desativado (`is_active = False`), não excluído.
- **Sem duplicidade (NF008):** restrições `unique` no banco para frequência, simulado, redação e turma. A importação deve usar `update_or_create` sobre essas chaves.
- **Perfil e contas (RN013, NF013):** só superusuário cria, altera ou exclui `Usuario` no admin, incluindo `perfil`, senha de terceiros, grupos e permissões. Staff sem superusuário tem no máximo leitura. As contas de superusuário são detidas pelos Diretores. O Diretor gere usuários nas telas de `Usuários` (RF002): cria, edita perfil e dados, revoga por desativação (`is_active`, sem exclusão) e gera link de uso único para definir a senha (gerar o link invalida a senha anterior, para que ninguém entre como outro usuário sem que ele perceba); nunca vê nem digita a senha de terceiros. Sempre resta um Diretor ativo, e superusuários ficam só no admin.
- **Auditoria (NF009):** toda alteração de `perfil`, `is_active`, e-mail e nome grava um `RegistroAlteracao` por campo (quem, quando, valor anterior e novo). Nunca guarda senha, hash ou token. O histórico só aparece para o Diretor.
- **Mudança de turma (RN011):** use `aluno.mudar_turma(nova_turma, data)`. O período anterior é fechado e outro é aberto. `aluno.turma_em(data)` responde em que turma o aluno estava numa data.

## Diferenças em relação ao DER do Lab 03

Registradas na SM #41, para atualizar o DER, o Diagrama de Classes e o Relatório Descritivo:

1. **Tabela `HistoricoTurma`** (aluno, turma, início, fim). O DER guarda só a turma atual, o que não atende à RN011. Esse problema foi apontado pela revisão estática do Plano de Testes.
2. **`Intervencao.aluno`**. No DER, a intervenção se liga só ao alerta, mas o RF019 admite intervenção sem alerta.
3. **`ResultadoSimulado.presente`**. Registra a ausência no simulado, que não é avaliada em desempenho (RN009). Um ausente não tem nota (restrição no banco).
4. **`ResultadoRedacao`**: `nota_competencias` virou cinco colunas (`nota_c1` a `nota_c5`). Também foram acrescentados `entregue` (já presente no Diagrama de Classes) e `tema`. O tema é identificado pela terça-feira em que foi lançado (RN007).
5. **`Alerta.regra`, `Alerta.ciclo` e `Alerta.area`**. Registram qual regra e qual limiar geraram o alerta e a área do alerta de desempenho (RF015).
6. **`CicloCalendario` sem `temaRedacaoSemana`**, com `data_simulado`. Cada ciclo tem duas semanas e, portanto, dois temas (RN007); os temas ficam na tabela `TemaRedacao`, e o ciclo registra a data do simulado (RN006).
7. **Tabela `RegistroAlteracao`** (autor, modelo, objeto, campo, valor anterior e novo). O DER não tem trilha de auditoria, exigida pela NF009.
8. **Tabelas `DiaCalendario` e `TemaRedacao`**. O DER não tem onde guardar feriados, recessos (RN005) nem os temas semanais (RN007).
9. **Tabela `PeriodoLetivo`** (RN005). Define os períodos de aula; as férias ficam entre dois períodos.
10. **`Aluno.situacao` e `Aluno.data_saida`** (RF006). Registram desligamento, evasão e lançamento inválido; o DER não tem situação do aluno.
11. **Tabela `RegistroImportacao`** (NF007, NF009). Trilha dos uploads de importação, sem conteúdo de arquivo.
12. **`inteligencia.RegraAlerta`**. Existe só no Diagrama de Classes, não no DER; guarda os limiares no banco (RF018).
13. **Tabela `PendenciaImportacao`** (RN003, NF006). Guarda as linhas de frequência, simulado e redação que não casaram com um aluno pela matrícula, até o Diretor associá-las ou descartá-las.

## Cadastro (RF006)

- **Colunas aceitas** (CSV `;` ou `,`, ou XLSX, primeira aba; cabeçalho sem distinção de caixa, acento ou espaço): `matricula`, `nome` (ou `nome_completo`, `aluno`), `turma` e, **opcional**, `data_ingresso` (ou `ingresso`, `data_de_ingresso`): se a coluna faltar ou a célula vier vazia, o aluno novo ingressa em 1º de janeiro do ano letivo informado e, em aluno existente, o ingresso não é conferido (preenchida e diferente, vira divergência). Datas em `dd/mm/aaaa` ou `aaaa-mm-dd`. Limites: 5 MB e 5.000 linhas.
- **Divergências**: a importação nunca sobrescreve nome nem data de ingresso de aluno existente (RN003); a diferença é listada e o Diretor corrige na edição manual. Nome só difere em caixa, acento ou espaço: não é divergência. Turma diferente da atual muda a turma na data informada no formulário, preservando o histórico (RN011) e auditando (NF009). Reimportar não duplica (NF008). Aluno ausente do arquivo não é alterado (NF007).
- **Matrícula**: única por ano, sem vínculo entre anos, imutável (chave). Digitada errada: o Diretor cria o aluno com a matrícula correta e marca o lançamento errado como `INVALIDO`; ele é preservado, mas escondido das listas por padrão e fora dos indicadores.
- **`Aluno.corrigir_ingresso(data)`**: atualiza `data_ingresso` e o início do primeiro período de turma; recusa data igual ou posterior ao fim desse período.
- **`Aluno.objects.ingressados_ate(data)`**: alunos com `data_ingresso <= data` (RN004). **`ativos()`**: `situacao = ATIVO`.
- **Situação do aluno** (diferença 10 da seção "Diferenças em relação ao DER do Lab 03", SM #41): `situacao` (`ATIVO`, `DESLIGADO`, `EVADIDO`, `INVALIDO`) e `data_saida`. `DESLIGADO` e `EVADIDO` exigem `data_saida >= data_ingresso`; `ATIVO` exige `data_saida` vazia; `INVALIDO` não exige data. A importação não altera a situação; a situação não altera o `HistoricoTurma`.
- **Modelos para download** (qualquer usuário autenticado): `alunos/importar/modelo.xlsx` e `.csv`, gerados em memória por `ingestao/modelos.py` (`gerar_modelo(nome, colunas, exemplos, formato)`, reutilizável por RF003 a RF005) com o cabeçalho canônico de `COLUNAS` e duas linhas sintéticas (matrícula `S9000xx`). O modelo baixado importa sem divergência.
- **LGPD**: conforme a SM #58, o Membro vê as listas de alunos e turmas, com nomes. Baixar os modelos de planilha é permitido ao Membro; importar cadastro e criar ou editar aluno ou turma é só do Diretor. Arquivos importados não são guardados.
- **Trilha de uploads** (`core.RegistroImportacao`, NF007): ao importar (não ao conferir) grava-se autor, data e hora, tipo, nome do arquivo (sanitizado, máx. 255), tamanho, ano letivo, data de mudança e as contagens do resumo. Nunca o conteúdo, nomes ou matrículas de alunos. Sem exclusão nem edição. Só o Diretor vê, em `importacoes/` (filtro `?usuario=`).

## Calendário (RF007)

- **Dia letivo (RN005)**: segunda a sexta dentro de um `PeriodoLetivo`, desde que não exista `DiaCalendario(letivo=False)` na data. `DiaCalendario(letivo=True)` é a exceção contrária (sábado com aula) e conta por si. O calendário do CASD tem aula de segunda a sexta e é preenchido aos poucos; por isso o Diretor cadastra períodos (vários por ano, sem sobreposição, sem modalidade: o início do semiextensivo já é coberto pela data de ingresso, RN004) e só as exceções (15 a 20 por ano). Use `core.calendario`: `eh_dia_letivo(data)`, `dias_letivos(inicio, fim)` (extremos inclusos, mesma regra). A regra é aplicada na hora do cálculo (RF003, RF010), nunca só na importação, porque um dia pode virar não letivo depois.
- **Ciclo (RN006)**: o que o calendário disser; sem restrição de 14 dias no banco (duração diferente gera aviso na importação e na edição). Pode haver lacunas (recesso de julho). Sobreposição é erro (`clean()`). `ciclo_em(data)` devolve o ciclo ou `None`. O número do ciclo não é armazenado: a tela numera pela ordem no ano. `data_simulado` é opcional e fica dentro do ciclo (restrição no banco).
- **Tema (RN007)**: chave na terça-feira (restrição no banco), vale de terça a segunda; terça de feriado continua tendo tema. `tema_em(data)` devolve o tema da terça anterior (janela de 7 dias) ou `None` na semana sem tema; `temas_do_ciclo(ciclo)`. `ResultadoRedacao` continua ligado por `tema_semana == TemaRedacao.data`; uma FK fica para o RF005.
- **Importação** (Diretor, `calendario/importar/`): tipos `periodos` (`inicio`, `fim`, `descricao` opcional; chave `inicio`, sobreposição recusada), `dias` (exceções; `data`, `dia_letivo` com S/N, sim/não, 1/0; `descricao` opcional), `ciclos` (`data_inicio`, `data_fim`, `data_simulado` opcional) e `temas` (`data`, `tema`). O ano letivo é informado e linha de outro ano é inconsistente. Diferente do cadastro, reimportar **atualiza** o que mudou e audita cada campo (NF009); o que não mudou conta como sem alteração (NF008); ausente do arquivo não é tocado (NF007). Modelos para download por tipo e formato em `calendario/importar/modelo/<tipo>/<csv|xlsx>/`. A trilha (`RegistroImportacao`) ganha os tipos `PERIODOS`, `CALENDARIO`, `CICLOS`, `TEMAS` e o campo `atualizados`.
- **Acesso**: qualquer autenticado lê o calendário e baixa os modelos; importar e editar é só do Diretor. Sem rota de exclusão (NF007). Não há dado pessoal.

## Base de importação (NF006, NF008, NF011, NF025)

Sem migração: é código compartilhado por todas as importações.

- **`ingestao/base.py`:** `ResumoImportacao` (criados, atualizados, sem alteração, inconsistentes, avisos, sobreposições) com os totais `importados`, `ignorados`, `divergentes` e `total_linhas`, que sempre fecha com as linhas do arquivo. "Ignorado" é só a linha válida que não mudou nada; a que difere do banco (divergência do cadastro) conta à parte. `triar` valida e separa linha inválida ou repetida sem interromper; `transacao_de_importacao(gravar)` desfaz tudo ao só conferir; `linha_isolada` usa um savepoint por linha (aplicado no cadastro e no calendário): uma restrição do banco ou uma validação do modelo recusa só aquela linha, que vira inconsistente, e o motivo nunca traz o valor da célula (mensagem com `params` vira o motivo genérico).
- **`ingestao/confirmacao.py` e `web/importacao.py`:** a tela sempre confere primeiro e só grava com o token da conferência, assinado (`django.core.signing`, validade de 30 minutos) e preso ao usuário, ao hash do arquivo, aos parâmetros do formulário e a cada contador do resumo (`assinatura()`: criados, atualizados, sem alteração, divergentes, inconsistentes, sobreposições; no cadastro, também mudanças de turma e turmas criadas). Assim, um registro "a criar" que passou a existir antes da confirmação não é sobrescrito sem nova conferência. Nada fica no servidor (nem arquivo, nem sessão). Se algo mudou, a gravação é desfeita e a tela volta a ser conferência, com aviso e token novo. A confirmação do resumo é a confirmação das sobreposições de dados já existentes (NF008).
- **Limite de linhas (NF025):** `settings.IMPORTACAO_LIMITE_LINHAS` (variável de ambiente de mesmo nome, padrão 5000); `ler_tabela(limite_linhas=...)` troca o valor por chamada. O valor é lido na chamada, não na importação do módulo.
- **Importação nova:** escreva `_validar(linha)` e a aplicação por linha; use `triar`, `transacao_de_importacao` e `linha_isolada`, devolva um `ResumoImportacao` e chame `executar_importacao` na view (`importar(linhas, gravar)` e `registrar(nome, tamanho, resumo)`), com `diretor_required`. Reaproveite os parciais `web/_importacao_resumo.html` e `web/_importacao_script.html`.
- **NF011:** `tests/test_importacao_web.py` mede conferir e confirmar 500 alunos em menos de 2 minutos.

## Pendências de importação (RN003, #69)

- **Quando:** nas importações de frequência (RF003), simulados (RF004) e redação (RF005), a linha cuja matrícula está em branco, fora do padrão, é de outro ano letivo, não existe no cadastro ou é de aluno `INVALIDO` vira uma `PendenciaImportacao` em vez de ser descartada. Nunca se adivinha o aluno pelo nome (RN003). No resumo, essas linhas aparecem em "Pendências" e entram no total de linhas.
- **`ingestao/pendencias.py`:** `LocalizadorAlunos(matriculas, ano).localizar(matricula)` devolve o aluno ou o motivo; `registrar_pendencia(...)` é idempotente pela `chave` (sha256 de origem, ano, matrícula e nome informados, este sem caixa nem acento, e da referência da origem: dia, ciclo ou tema). Reimportar a mesma linha reencontra a pendência e atualiza `dados`; se ela já foi associada ou descartada, a linha é ignorada (NF008).
- **Associação** (`associar(pendencias, aluno, autor=..., confirmar_nome=False)`): em grupo, para as linhas do mesmo aluno. Recusa aluno `INVALIDO` ou de outro ano letivo. Se algum nome informado difere do cadastro (caixa, acento e espaço à parte), exige `confirmar_nome`. Cada importação registra com `@aplicador(origem)` a função que grava o que a linha traria (`dados`); ela roda num savepoint, e a recusa ou a restrição do banco deixa só aquela pendência como estava.
- **Descarte** (`descartar`): a pendência fica `DESCARTADA`, preservada (NF007).
- **Auditoria (NF009):** associar e descartar gravam `RegistroAlteracao` só do campo `situacao`; quem e quando ficam em `resolvida_por` e `resolvida_em`. Nunca nome, matrícula ou notas na auditoria nem nas mensagens (as mensagens podem ir para o cookie de mensagens).
- **Tela:** `pendencias/`, só do Diretor (RN013), com filtro por origem, situação e ano. O nome do cadastro aparece só na própria página, quando a associação pede confirmação.
- **Trilha:** `RegistroImportacao.pendencias` conta as linhas que viraram pendência; os tipos `FREQUENCIA`, `SIMULADOS` e `REDACOES` ficam prontos para RF003 a RF005. `web.importacao.registrar_trilha` grava a trilha a partir do resumo.

## Frequência da catraca (RF003, #14)

- **Arquivo:** uma linha por **passagem**: `data` (aceita `dd/mm/aaaa hh:mm`, a hora é ignorada), `matricula` e, opcional, `nome`. O Diretor informa o ano letivo e o período (`inicio` e `fim`, dentro do ano). Limite próprio de linhas: `IMPORTACAO_LIMITE_LINHAS_CATRACA` (padrão 50.000, cerca de dois meses de 900 alunos). Modelo para download em `frequencia/importar/modelo/<csv|xlsx>/`, com o ano atual.
- **Apuração (RN001):** para cada aluno do ano (turma do ano letivo, sem `INVALIDO`, entre o ingresso e a saída, RN004) e cada dia de `dias_letivos(inicio, fim)` (RN005), um `RegistroFrequencia`: `presente` se houve ao menos uma passagem, ausente se não houve. Não há tolerância de atraso: o arquivo não é lido por hora.
- **Avisos:** passagem em dia não letivo não vira registro, mas gera aviso por dia ("dia não letivo com N passagens; o calendário está atualizado?"); também passagem antes do ingresso ou depois da saída, nenhum período letivo cadastrado e "calendário definido até dd/mm" quando o último período termina antes do fim informado.
- **Linhas:** data em branco, inválida ou fora do período é inconsistente; várias passagens do mesmo aluno no dia contam uma presença (as demais são ignoradas). Matrícula sem aluno vira pendência (`FREQUENCIA`, referência = dia); a mesma pessoa passando várias vezes no dia gera uma pendência só.
- **Reimportação (NF008):** substitui `presente` dos registros existentes do período, com `RegistroAlteracao` por registro alterado (NF009), e nunca altera `justificada` (RN002). O resumo lista a sobreposição ("N registros já existem…"); confirmar a conferência é confirmar a substituição. Pendência já associada conta como passagem do aluno; já resolvida é ignorada.
- **Associação de pendência:** marca o aluno presente naquele dia (cria ou altera o registro, com auditoria). Recusa dia não letivo ou fora da janela do aluno.
- **Gravação em lote:** `bulk_create` e `bulk_update` em lotes de 2.000 (NF011).

## Simulados do P+ (RF004, #15)

- **Arquivo:** uma linha por aluno e simulado: `data`, `matricula`, `nome` (opcional), `presenca` (`Presente`/`Ausente`, também S/N), `simulado` (opcional, não é guardado) e, por área (`lc`, `ch`, `cn`, `mt`), `<area>_acertos` e `<area>_tri` (RN010). Modelo para download em `simulados/importar/modelo/<csv|xlsx>/`, com o ano atual.
- **Ciclo (RN006):** o ciclo do ano cuja `data_simulado` é a data da linha ou, se nenhum, o que contém a data. Sem ciclo, a linha é inconsistente: os ciclos precisam ser cadastrados antes.
- **Valores:** acertos de 0 a 45 por área; TRI de 0 a 1000 com uma casa decimal (vírgula ou ponto). Presente exige as oito notas; ausente (RN009) não pode ter nota e grava as quatro áreas com `presente=False` e sem nota. Simulado antes do ingresso (RN004) ou depois da saída do aluno é inconsistente; aluno repetido no mesmo simulado também.
- **Reimportação:** atualiza o que mudou, com `RegistroAlteracao` por campo (NF009); o resumo avisa quantos alunos já tinham resultado (NF008). Conta linhas: criada, atualizada ou sem alteração.
- **Pendências (RN003):** referência = ciclo; `dados` guarda presença e notas. Associar grava as quatro áreas para o aluno e recusa se ele já tem resultado no simulado ou se o simulado é de fora da janela dele.
- **Datas do ciclo fixas:** `CicloCalendario.clean()` recusa mudar `data_inicio`, `data_fim` ou `data_simulado` de ciclo que já tem resultado de simulado. Vale para a tela e para a importação do calendário (`docs/dominio-casd.md`, seção 4).

## Suposições a confirmar

- **Áreas do simulado:** as quatro áreas do ENEM (Linguagens, Humanas, Natureza, Matemática). Confirmar com a DES como o P+ separa as áreas, sobretudo nos simulados de FUVEST.
- **Formato da matrícula:** confirmado em 16/11/2026. É sempre de 7 dígitos: `AA` (ano letivo) + `30` (extensivo) ou `31` (semiextensivo) + 3 dígitos, e o aluno recebe uma matrícula nova a cada ano. Detalhes em [dominio-casd.md](dominio-casd.md), seção 2. O campo continua como texto de até 20 caracteres, o que também comporta o formato da base sintética.
