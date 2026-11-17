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
4. **`ResultadoRedacao`**: `nota_competencias` virou cinco colunas (`nota_c1` a `nota_c5`), decimais com uma casa (a banca VUNESP do Corrija-me dá notas como 21,4). Também foram acrescentados `entregue` (já presente no Diagrama de Classes), `tema`, `banca` e `nota_final`. O tema é identificado pela terça-feira em que foi lançado (RN007).
5. **`Alerta.regra`, `Alerta.ciclo`, `Alerta.area`, `Alerta.semana` e `Alerta.ativo`**. Registram qual regra e qual limiar geraram o alerta, a área do alerta de desempenho (RF015), a semana do alerta de frequência (NF005) e se ele ainda vale depois de uma correção dos dados (NF007).
6. **`CicloCalendario` sem `temaRedacaoSemana`**, com `data_simulado`. Cada ciclo tem duas semanas e, portanto, dois temas (RN007); os temas ficam na tabela `TemaRedacao`, e o ciclo registra a data do simulado (RN006).
7. **Tabela `RegistroAlteracao`** (autor, modelo, objeto, campo, valor anterior e novo). O DER não tem trilha de auditoria, exigida pela NF009.
8. **Tabelas `DiaCalendario` e `TemaRedacao`**. O DER não tem onde guardar feriados, recessos (RN005) nem os temas semanais (RN007).
9. **Tabela `PeriodoLetivo`** (RN005). Define os períodos de aula; as férias ficam entre dois períodos.
10. **`Aluno.situacao` e `Aluno.data_saida`** (RF006). Registram desligamento, evasão e lançamento inválido; o DER não tem situação do aluno.
11. **Tabela `RegistroImportacao`** (NF007, NF009). Trilha dos uploads de importação, sem conteúdo de arquivo.
12. **`inteligencia.RegraAlerta`**. Existe só no Diagrama de Classes, não no DER; guarda os limiares no banco (RF018).
13. **Tabela `PendenciaImportacao`** (RN003, NF006). Guarda as linhas de frequência, simulado e redação que não casaram com um aluno pela matrícula, até o Diretor associá-las ou descartá-las.

14. **Tabela `relatorios.NotificacaoCiclo`** (RF017). Registra que o e-mail de fechamento de um ciclo já foi enviado, para o envio ocorrer uma só vez por ciclo. O DER não tem onde guardar isso.

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
- **Tema (RN007)**: chave na terça-feira (restrição no banco), vale de terça a segunda; terça de feriado continua tendo tema. `tema_em(data)` devolve o tema da terça anterior (janela de 7 dias) ou `None` na semana sem tema; `temas_do_ciclo(ciclo)`. `ResultadoRedacao` continua ligado por `tema_semana == TemaRedacao.data`, sem FK: a importação do RF005 garante que o `TemaRedacao` da terça existe antes de gravar a redação.
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

## Planilhas reais (#74)

As três importações leem os layouts das planilhas que o CASD usa no dia a dia, descritos em `docs/dominio-casd.md` (seção 6). Cabeçalhos e geradores ficam em `ingestao/planilhas_casd.py`; as réplicas sintéticas, em `tests/dados_sinteticos/pequena/2026/planilhas/`. A associação continua pela matrícula (RN003): a equipe acrescentou a coluna `Matrícula` à grade e ao relatório do P+, e no Corrija-me usa a coluna `RM`. Os modelos para download são `.xlsx` no layout real, com linhas sintéticas do ano atual. A leitura aceita `.xlsm` (as macros nunca rodam) e escolhe a aba pelo nome (`ler_tabela(aba=...)`, `ler_bruto`). `executar_importacao(ler=...)` recebe o leitor das planilhas que não são uma tabela simples.

Em todas as três, uma pendência já associada vale para o aluno escolhido nas reimportações seguintes (`pendencias.aluno_da_linha`); já descartada, a linha é ignorada.

## Frequência: grade "Presença Anual" (RF003, #14)

- **Arquivo:** a planilha `Controle de Presença AAAA.xlsx`, aba "Presença Anual" (o formulário aceita outro nome, como "Nivelamento"). O cabeçalho é a primeira das dez linhas iniciais com `Nome` e `Matrícula`; cada coluna cujo cabeçalho é uma data (ou `dd/mm`, completada com o ano letivo) é um dia. As outras colunas (`Turma`, `% Presença`, `Faltas`) são ignoradas, assim como linhas sem matrícula e sem nome com P, F ou J (título, totais, médias). Até 500 colunas.
- **Códigos (RN001, RN002):** `P` grava presente; `F` grava falta sem justificativa; `J` grava falta justificada; `S` (sem aula) não grava. A grade manda: reimportar troca F por J ou P conforme a planilha, com `RegistroAlteracao` por campo (NF009). Exceção (RF008, #17, provisória até a equipe confirmar): `F` sobre uma falta já justificada no FAROL não a desfaz; vale como `J` e o resumo avisa quantas foram mantidas (`justificativas_mantidas`). `P` continua valendo sobre a justificada.
- **Calendário (RN005) e janela do aluno (RN004):** só entram dias letivos de `dias_letivos` e entre o ingresso e a saída. Avisos por dia: P, F ou J em dia não letivo ("o calendário está atualizado?") e S em dia letivo. Avisos gerais: registros fora da janela do aluno, dias letivos sem coluna na grade, códigos desconhecidos, colunas de outro ano, nenhum período letivo e "calendário definido até dd/mm".
- **Resumo:** conta linhas de aluno (novo, com alteração, sem alteração, pendência, inconsistente: aluno repetido) e, à parte, registros criados, alterados e iguais, presenças, faltas e justificadas. A sobreposição lista os registros já existentes no período da grade; confirmar a conferência é confirmar a substituição (NF008). Aluno ausente da grade não é tocado (NF007).
- **Pendência:** uma por linha (`referencia = "grade"`), com os códigos da linha em `dados`; associar grava os P, F e J aplicáveis para o aluno.

## Justificativa de falta (RF008, #17)

- **Tela:** `alunos/<matricula>/faltas/` (`web/justificativas.py`), só do Diretor (RN013), com link na ficha do aluno. Lista as faltas (`RegistroFrequencia` com `presente=False`) em dia letivo (`core.calendario`, RN005) e dentro da janela do aluno (RN004), da mais recente à mais antiga.
- **Regra (`ingestao/justificativas.py`):** registrar a justificativa é aprová-la (RN002: "aprovada pela Direção"); a falta justificada conta como presença. Só se justifica falta que já existe como registro: a tela não cria `RegistroFrequencia`. Retirar a justificativa é permitido. Presença, dia não letivo e dia fora da janela são recusados.
- **Sem campo novo e sem migração:** usa `RegistroFrequencia.justificada`. O motivo não é guardado (sem texto livre); a trilha é o `RegistroAlteracao` (autor, data e valor anterior, NF009). Repetir a ação não audita.
- **Alerta:** ao mudar, a view regenera o alerta de frequência da semana (RF014); o mesmo registro é desativado ou reativado (NF005, NF007).
- **Importação da grade:** `F` não desfaz a justificativa (ver "Códigos"); a decisão é provisória (pergunta B1) e fica isolada em `ingestao.frequencia._mantem_justificada`.

## Simulados: relatório do P+ (RF004, #15)

- **Arquivo:** o relatório de **uma** avaliação (`.xlsm` ou `.xlsx`). Abas `Resultados e Classificações TRI` (com `Matrícula`, `ID Aluno`, `Nome Avaliação`, `Nome Aluno` e `<Área> - Etapa N - Nota`) e `Acertos e Porcentagens TRI` (`ID Aluno` e `<Área> - Acertos`), unidas pelo `ID Aluno`. CSV não serve: são duas abas.
- **Ciclo (RN006):** o P+ não traz data; o Diretor escolhe o ciclo no formulário (do ano letivo informado). A janela do aluno (RN004) usa a data do simulado do ciclo (ou o fim do ciclo).
- **Etapas e ausência (RN009, RN010):** área com nota e acertos em branco é falta naquela etapa (Etapa 1: LC e CH; Etapa 2: CN e MT): grava `presente=False`, sem nota, só nas áreas da etapa. Faltou às duas: ausente. Só um dos dois em branco é inconsistente. Acertos de 0 a 45; TRI de 0 a 1000, uma casa decimal.
- **Linhas inconsistentes:** outra avaliação (o `Nome Avaliação` difere do mais frequente), aluno sem linha na aba de acertos, aluno repetido, simulado fora da janela.
- **Reimportação e pendência:** como antes (auditoria por campo; referência = ciclo; associar grava as quatro áreas e recusa se o aluno já tem resultado no ciclo). As datas de ciclo com resultados são fixas (`CicloCalendario.clean()`).

## Redações: exportação do Corrija-me (RF005, #16)

- **Arquivo:** a aba `Worksheet` exportada, de **um** tema, com `RM` (matrícula), `NOME COMPLETO`, `BANCA`, `TEMA`, `C1`–`C5`, `NOTAL FINAL` (sic), `ID DA ATIVIDADE` e `DATA ENVIO`; as demais colunas são ignoradas. O Diretor escolhe a terça do tema (RN007), porque o arquivo não traz a data do tema.
- **Tema:** se não há `TemaRedacao` na terça, ele é criado com o título mais frequente do arquivo; se há, o cadastrado é mantido, com aviso quando o título difere. Sem tema e sem título, todas as linhas são inconsistentes.
- **Banca:** ENEM (ou banca em branco) exige C1 a C5, de 0 a 200, e a nota final, se vier, tem de ser a soma (tolerância de 0,5). Outras bancas (VUNESP, usada no CASDinho) exigem C1 a C4, aceitam decimais e guardam a nota final da banca. `ResultadoRedacao` ganhou `banca` e `nota_final`, e as competências viraram decimais com uma casa (migração 0009); `nota_total` é a nota final ou, sem ela, a soma das cinco.
- **Não entregue:** o Corrija-me só exporta entregas. Aluno do ano (não `INVALIDO`), no curso na semana do tema (RN004) e sem linha no arquivo ganha `entregue=False`, sem nota; registro já existente não é tocado. Associar uma pendência a ele troca o não entregue pela redação, com auditoria.
- **Linhas:** reenvio do mesmo aluno vale o mais recente (`DATA ENVIO`) e os demais contam como ignorados; outra atividade (`ID DA ATIVIDADE` diferente do mais frequente) e tema fora da janela do aluno são inconsistentes.
- **Reimportação e pendência:** auditoria por campo; referência = terça do tema.

## Indicadores (#18, #19)

- **`inteligencia/indicadores.py`:** funções de regra puras, sem banco nem tela. Cada decisão tem teste.
  - **Frequência:** `frequencia(dias, letivos=..., ingresso=..., saida=...)` conta só dias letivos do calendário na hora do cálculo (RN005) e só da janela do aluno (RN004). Falta é o dia sem presença (RN001); a ausência justificada conta como presença na taxa (RN002). `Frequencia` traz dias, presenças, justificadas, faltas não justificadas, `taxa` e `percentual`.
  - **Desempenho:** `notas_por_ciclo` monta o histórico (área ausente = `None`, RN009). `nota_total` é a média TRI das quatro áreas e só existe com as quatro (RN010, RN009). `delta(valores, ciclo)` compara com o último ciclo anterior em que o aluno foi avaliado (RN008); no primeiro simulado ou num ciclo em que faltou, não há delta. `classificar(variacao, limiar)`: queda se a variação é menor ou igual a -limiar, evolução se é maior ou igual a +limiar, estagnado entre os dois.
  - **Redação:** `participacao(entregas)` dá entregues sobre registradas.
- **`inteligencia/consultas.py`:** carrega em lote do banco (frequências, turma na data pelo histórico, RN011, históricos de notas, participações) e aplica as funções acima.
- **Base sintética no banco de desenvolvimento:** `uv run python manage.py carregar_base_sintetica --autor <diretor>` (só com `DEBUG`) carrega cadastro, calendário, a grade de presença (pela importação real), todos os simulados e todas as redações de 2026, para ver o painel com dados.

## Alertas (#24, #25, #26)

- **Regras (`inteligencia.RegraAlerta`):** uma ativa por tipo, com limiar e descrição em linguagem simples (NF021). Valores padrão em `config/regras_padrao.yaml` (IC-10), carregados pela migração de dados `inteligencia.0002` só quando não há regra ativa do tipo; depois, o limiar vive no banco (RF018). `inteligencia.regras.vigente(tipo)` devolve a regra ativa; sem ela, nada é gerado.
- **Frequência (RF014), por semana de segunda a domingo:** faltas não justificadas em dias letivos (`consultas.frequencias`, RN001, RN002, RN005) maiores ou iguais ao limiar. O motivo cita as faltas, a semana, os dias letivos e o limiar.
- **Desempenho (RF015), por ciclo:** queda quando a nota total (média das quatro áreas) ou alguma área cai pelo menos o limiar em relação ao último simulado em que o aluno foi avaliado (RN008). Quem faltou não é avaliado (RN009); no primeiro simulado não há alerta. A `area` é vazia quando a nota total caiu; senão, é a área da maior queda. O motivo lista cada queda (antes → depois e a diferença) e o limiar.
- **NF005 e NF007:** no máximo um alerta por aluno, tipo e semana (`semana`) ou ciclo (`ciclo`), com restrição no banco. Regerar atualiza o mesmo alerta; o que deixou de valer fica `ativo=False`, sem exclusão.
- **Quando são gerados:** ao confirmar a importação da grade de presença (as semanas da grade) e do P+ (todos os ciclos do ano, porque um ciclo novo muda o delta do seguinte); ao associar pendências; na carga da base sintética; e por `manage.py gerar_alertas --ano AAAA`, que é idempotente e pode rodar por agendador.
- **Indicativos (RN012, NF022):** nenhum alerta muda nada no aluno; servem para a Direção olhar.

## Painel, indicadores e ficha (#20 a #23)

- **Referência (`inteligencia.painel.referencia`):** o ano com dados mais recente, a última semana com frequência e o último ciclo com resultado de simulado. É o "ciclo corrente" para os dados já importados.
- **Painel inicial (RF010, `/`):**
  - alertas ativos de frequência (semanas do ciclo de referência até a última semana com dados) e de desempenho (do ciclo de referência);
  - presença e redações entregues no período;
  - situação de cada turma, pela turma da data (RN011): alunos, presença, queda, estagnados, em evolução (classificação do RF015 pelo limiar vigente), sem avaliação no ciclo (faltou ou primeiro simulado, RN009) e sem presença no ciclo (só faltas não justificadas nos dias letivos).
  - Sem dados no ano, mostra a data da última importação de cada tipo.
  - O Diretor clica numa contagem e abre a lista (`painel/<categoria>/`, nominal, só Diretor); o Membro vê só os números (RN013). Alertas a um clique e a ficha a dois (NF002). O texto do painel lembra que os alertas são indicativos (RN012, NF022).
- **Indicadores agregados (RF012, `indicadores/`):** Diretor e Membro, sem nome. Filtros por turma, área e ciclo. Mostra:
  - gráficos por ciclo da nota TRI média dos avaliados (total ou da área) e da presença;
  - detalhe do ciclo por turma (nota, avaliados, presença, redações, quedas e evoluções);
  - tabela da evolução no tempo.
- **Ficha do aluno (RF011, RF013, `alunos/<matrícula>/ficha/`):** só o Diretor. Traz:
  - notas por ciclo e por área, com o delta contra o próprio histórico e a classificação (RN008);
  - a média da turma no ciclo só como referência, nunca para classificar;
  - frequência por ciclo, alertas (inclusive os desativados), intervenções, redações e histórico de turmas.
- **Gráficos:** SVG gerado no servidor (`web/graficos.py`), sem JavaScript nem CDN; escala com a tela (NF001) e escapa todo texto.

## Relatório de auxílios (RF021, #33, SM #80)

- **Nenhum modelo novo e nada gravado (opção A da SM #80).** Não existe `Beneficio`, nem campo de auxílio no `Aluno`: ser beneficiado é dado socioeconômico e nunca é persistido (NF015, escopo "não fará").
- **Fluxo (`relatorios/auxilios/`, só Diretor):** o arquivo (só a coluna matrícula, até 1 MB) é lido em memória, o relatório é calculado na hora (`relatorios.auxilios.calcular`) e descartado com a resposta. Sem `RegistroImportacao`, `PendenciaImportacao`, `RegistroAlteracao`, sessão, log ou arquivo em disco. Para o upload não passar por arquivo temporário, a view usa só o tratador de memória.
- **Conteúdo:** compara beneficiados e demais alunos do ano, no período de referência do painel: número de alunos, frequência, participação nas redações, classificação no último ciclo, alunos com alerta ativo e intervenções por desfecho. O bloco agregado não traz nome nem matrícula; a lista nominal é separada.
- **Matrículas:** validadas com `validar_matricula` (outro ano e fora do padrão são recusadas, só com número da linha e motivo). Matrícula sem aluno é só contada.

## Limiares das regras (RF018, #28)

- **Tela `regras/`:** todos veem as regras ativas, com o limiar e a descrição em linguagem simples (NF021), e os limiares anteriores. Só o Diretor altera (`regras/<tipo>/`).
- **Faixas aceitas:** frequência, de 1 a 7 faltas, inteiro; desempenho, de 1 a 500 pontos, com até duas casas.
- **Pré-visualização obrigatória:** a tela mostra quantos alunos seriam sinalizados com o limiar atual e com o novo. Na frequência, conta as semanas do ciclo de referência; no desempenho, o ciclo de referência (`alertas.simular_*`, sem gravar). "Salvar" só vale para o mesmo valor pré-visualizado.
- **Troca (`regras.alterar_limiar`):** desativa a regra vigente e cria outra, com a descrição gerada a partir de `config/regras_padrao.yaml`. Os alertas antigos continuam apontando para o limiar que os gerou. Audita com `RegistroAlteracao`: `ativa` da regra antiga e `limiar` anterior e novo da nova, com autor e data (NF009). Em seguida, os alertas do ano são regerados (`alertas.gerar_ano`).

## Notificação de ciclo (RF017, #32)

- **`relatorios.NotificacaoCiclo`** (`HistoricoPreservado`, diferença 14 da SM #41): `ciclo` (um para um) e `destinatarios` (só a contagem). Não guarda endereços nem o corpo; `criado_em` é a data do envio. É a garantia de idempotência: um e-mail por ciclo.
- **Comando `notificar_ciclo`** (`--data AAAA-MM-DD`, `--reenviar`): envia o e-mail do ciclo mais recente já fechado (`data_fim < hoje`) e com resultados de simulado. Não regera alertas: rode `gerar_alertas` antes. Ciclos antigos não notificados são ignorados.
- **Conteúdo:** só números agregados e nomes de turma (total, frequência, participação, queda, estagnados, evolução, sem avaliação, sem presença, alertas ativos), sem nome nem matrícula (RN013, NF013). Texto puro, com o aviso de que alertas são indicativos (RN012). O link do painel só aparece com `SITE_URL` definido.
- **Destinatários:** usuários ativos com e-mail, exceto superusuários (Diretor e Membro). Uma mensagem por destinatário. Se o SMTP falhar, o registro é desfeito; sem destinatários, nada é registrado.

## Histórico de intervenções (RF020, #31)

- **Tela `intervencoes/`:** só do Diretor (RN013, NF013); o Membro recebe 403. A lista não edita nada nem exclui (NF007), mas leva ao registro do desfecho (RF019, #30). Não há migração.
- **Escopo:** todas as intervenções, de todos os anos e gestões, inclusive de alunos não ativos e de usuários revogados. Ordem `-data, -id`, 50 por página; os links de página preservam os filtros.
- **Filtros (GET):** `aluno` (matrícula exata ou parte do nome; é busca de consulta, não associação, RN003), `tipo`, `desfecho` (inclui `PENDENTE`, o desfecho ainda em branco) e período `de`/`ate` sobre `Intervencao.data`, inclusivo nas duas pontas. `de` posterior a `ate` é erro de formulário e a lista fica vazia.

## Registro de intervenções (RF019, #30)

- **Rotas:** `alunos/<matrícula>/intervencoes/nova/` registra; `intervencoes/<id>/desfecho/` registra ou atualiza o desfecho. As duas são só do Diretor (RN013, NF013), no GET e no POST. Não há migração.
- **Campos:** tipo, data (não futura), responsável (começa com o nome do usuário logado), descrição, alerta de origem opcional e desfecho opcional. `aluno` e `usuario` (quem registrou) nunca vêm do POST. Só os alertas do próprio aluno podem ser a origem, inclusive os que não valem mais; `?alerta=<id>` pré-seleciona o alerta e é ignorado se inválido ou de outro aluno.
- **Alunos:** `INVALIDO` não recebe intervenção (404); `DESLIGADO` e `EVADIDO` recebem.
- **Auditoria (NF009):** criar não gera `RegistroAlteracao`, pois autor e data já ficam em `usuario` e `criado_em`. Mudar o desfecho grava uma linha (campo `desfecho`, valores anterior e novo, autor), sem texto livre.
- **Depois de criada:** só o desfecho muda; desfecho definido pode trocar de valor, mas não volta a pendente. Sem exclusão (NF007).
- **RN012:** registrar não altera a situação do aluno nem o alerta; a tela avisa que a intervenção não é punição.

## Suposições a confirmar

- **Limiares dos alertas:** provisórios até a definição com a Direção (FAROL_Contexto, "Questões em aberto", itens 2 e 3). Frequência: 3 faltas não justificadas na semana; desempenho: queda de 30 pontos TRI. Evolução no RF015 usa o mesmo limiar para cima. O Diretor muda os limiares no sistema (RF018).
- **Evolução consistente (RF016, #27):** critério ainda não definido com a Direção; não implementado.
- **"Sem presença no ciclo" no painel:** aluno com dias letivos no ciclo e nenhuma presença (nem justificada). É a leitura provisória de "alunos inativos" do RF010; confirmar com a Direção.

- **Áreas do simulado:** as quatro áreas do ENEM (Linguagens, Humanas, Natureza, Matemática). Confirmar com a DES como o P+ separa as áreas, sobretudo nos simulados de FUVEST.
- **Formato da matrícula:** confirmado em 16/11/2026. É sempre de 7 dígitos: `AA` (ano letivo) + `30` (extensivo) ou `31` (semiextensivo) + 3 dígitos, e o aluno recebe uma matrícula nova a cada ano. Detalhes em [dominio-casd.md](dominio-casd.md), seção 2. O campo continua como texto de até 20 caracteres, o que também comporta o formato da base sintética.
