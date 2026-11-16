# Modelo de dados

Implementação física do Diagrama de Classes e do DER do Relatório Descritivo (Seções 1.4 e 1.5). Os modelos ficam em `core/models.py` e `inteligencia/models.py`.

| Modelo | Tabela do DER | Observações |
|---|---|---|
| `core.Usuario` | Usuário | Perfil Diretor ou Membro; padrão Membro (RN013) |
| `core.Turma` | Turma | Única por nome e ano letivo |
| `core.Aluno` | Aluno | Matrícula é a chave primária (RN003); `turma` é a turma atual |
| `core.HistoricoTurma` | **nova** | Períodos do aluno em cada turma (RN011) |
| `core.DiaCalendario` | **nova** | Um registro por dia: letivo ou não, com descrição (RN005) |
| `core.CicloCalendario` | Ciclo | Duas semanas entre simulados (RN006); `data_simulado` dentro do ciclo |
| `core.TemaRedacao` | **nova** | Tema semanal, chave na terça-feira (RN007) |
| `core.RegistroFrequencia` | Frequência | Único por aluno e dia (NF008) |
| `core.ResultadoSimulado` | Simulado | Único por aluno, ciclo e área; campo `presente` (RN009) |
| `core.ResultadoRedacao` | Redação | Único por aluno e tema; competências c1 a c5 (0 a 200) |
| `core.Alerta` | Alerta | Motivo obrigatório (NF004); guarda a regra e o ciclo que o geraram |
| `core.Intervencao` | Intervenção | Ligada ao aluno e, opcionalmente, ao alerta (RF019) |
| `core.RegistroAlteracao` | **nova** | Auditoria: autor, data, campo, valor anterior e novo (NF009); reutilizada por RF008 e RF018 |
| `inteligencia.RegraAlerta` | (só no Diagrama de Classes) | Uma regra ativa por tipo; limiares no banco (RF018) |

## Garantias

- **Sem exclusão física (NF007):** todos os modelos acima, menos `Usuario`, herdam de `core.historico.HistoricoPreservado`. `delete()` gera `ExclusaoProibidaError`, tanto no objeto quanto em querysets. As chaves estrangeiras usam `PROTECT`. Um usuário de gestão anterior é desativado (`is_active = False`), não excluído.
- **Sem duplicidade (NF008):** restrições `unique` no banco para frequência, simulado, redação e turma. A importação deve usar `update_or_create` sobre essas chaves.
- **Perfil e contas (RN013, NF013):** só superusuário cria, altera ou exclui `Usuario` no admin, incluindo `perfil`, senha de terceiros, grupos e permissões. Staff sem superusuário tem no máximo leitura. As contas de superusuário são detidas pelos Diretores. O Diretor gere usuários nas telas de `Usuários` (RF002): cria, edita perfil e dados, revoga por desativação (`is_active`, sem exclusão) e gera link de uso único para definir a senha (gerar o link invalida a senha anterior, para que ninguém entre como outro usuário sem que ele perceba); nunca vê nem digita a senha de terceiros. Sempre resta um Diretor ativo, e superusuários ficam só no admin.
- **Auditoria (NF009):** toda alteração de `perfil`, `is_active`, e-mail e nome grava um `RegistroAlteracao` por campo (quem, quando, valor anterior e novo). Nunca guarda senha, hash ou token. O histórico só aparece para o Diretor.
- **Mudança de turma (RN011):** use `aluno.mudar_turma(nova_turma, data)`. O período anterior é fechado e outro é aberto. `aluno.turma_em(data)` responde em que turma o aluno estava numa data.

## Diferenças em relação ao DER do Lab 03

Precisam de uma Solicitação de Mudança para atualizar o DER e o Relatório Descritivo:

1. **Tabela `HistoricoTurma`** (aluno, turma, início, fim). O DER guarda só a turma atual, o que não atende à RN011. Esse problema foi apontado pela revisão estática do Plano de Testes.
2. **`Intervencao.aluno`**. No DER, a intervenção se liga só ao alerta, mas o RF019 admite intervenção sem alerta.
3. **`ResultadoSimulado.presente`**. Registra a ausência no simulado, que não é avaliada em desempenho (RN009). Um ausente não tem nota (restrição no banco).
4. **`ResultadoRedacao`**: `nota_competencias` virou cinco colunas (`nota_c1` a `nota_c5`). Também foram acrescentados `entregue` (já presente no Diagrama de Classes) e `tema`. O tema é identificado pela terça-feira em que foi lançado (RN007).
5. **`Alerta.regra`, `Alerta.ciclo` e `Alerta.area`**. Registram qual regra e qual limiar geraram o alerta e a área do alerta de desempenho (RF015).
6. **`CicloCalendario` sem `temaRedacaoSemana`**, com `data_simulado`. Cada ciclo tem duas semanas e, portanto, dois temas (RN007); os temas ficam na tabela `TemaRedacao`, e o ciclo registra a data do simulado.
7. **Tabela `RegistroAlteracao`** (autor, modelo, objeto, campo, valor anterior e novo). O DER não tem trilha de auditoria, exigida pela NF009.
8. **Tabelas `DiaCalendario` e `TemaRedacao`**. O DER não tem onde guardar feriados, recessos (RN005) nem os temas semanais (RN007).

## Cadastro (RF006)

- **Colunas aceitas** (CSV `;` ou `,`, ou XLSX, primeira aba; cabeçalho sem distinção de caixa, acento ou espaço): `matricula`, `nome` (ou `nome_completo`, `aluno`), `turma` e, **opcional**, `data_ingresso` (ou `ingresso`, `data_de_ingresso`): se a coluna faltar ou a célula vier vazia, o aluno novo ingressa em 1º de janeiro do ano letivo informado e, em aluno existente, o ingresso não é conferido (preenchida e diferente, vira divergência). Datas em `dd/mm/aaaa` ou `aaaa-mm-dd`. Limites: 5 MB e 5.000 linhas.
- **Divergências**: a importação nunca sobrescreve nome nem data de ingresso de aluno existente (RN003); a diferença é listada e o Diretor corrige na edição manual. Nome só difere em caixa, acento ou espaço: não é divergência. Turma diferente da atual muda a turma na data informada no formulário, preservando o histórico (RN011) e auditando (NF009). Reimportar não duplica (NF008). Aluno ausente do arquivo não é alterado (NF007).
- **Matrícula**: única por ano, sem vínculo entre anos, imutável (chave). Digitada errada: o Diretor cria o aluno com a matrícula correta e marca o lançamento errado como `INVALIDO`; ele é preservado, mas escondido das listas por padrão e fora dos indicadores.
- **`Aluno.corrigir_ingresso(data)`**: atualiza `data_ingresso` e o início do primeiro período de turma; recusa data igual ou posterior ao fim desse período.
- **`Aluno.objects.ingressados_ate(data)`**: alunos com `data_ingresso <= data` (RN004). **`ativos()`**: `situacao = ATIVO`.
- **Situação do aluno** (Solicitação de Mudança do DER): `situacao` (`ATIVO`, `DESLIGADO`, `EVADIDO`, `INVALIDO`) e `data_saida`. `DESLIGADO` e `EVADIDO` exigem `data_saida >= data_ingresso`; `ATIVO` exige `data_saida` vazia; `INVALIDO` não exige data. A importação não altera a situação; a situação não altera o `HistoricoTurma`.
- **Modelos para download** (qualquer usuário autenticado): `alunos/importar/modelo.xlsx` e `.csv`, gerados em memória por `ingestao/modelos.py` (`gerar_modelo(nome, colunas, exemplos, formato)`, reutilizável por RF003 a RF005) com o cabeçalho canônico de `COLUNAS` e duas linhas sintéticas (matrícula `S9000xx`). O modelo baixado importa sem divergência.
- **LGPD**: conforme a SM #58, o Membro vê as listas de alunos e turmas, com nomes. Baixar os modelos de planilha é permitido ao Membro; importar cadastro e criar ou editar aluno ou turma é só do Diretor. Arquivos importados não são guardados.
- **Trilha de uploads** (`core.RegistroImportacao`, NF007): ao importar (não ao conferir) grava-se autor, data e hora, tipo, nome do arquivo (sanitizado, máx. 255), tamanho, ano letivo, data de mudança e as contagens do resumo. Nunca o conteúdo, nomes ou matrículas de alunos. Sem exclusão nem edição. Só o Diretor vê, em `importacoes/` (filtro `?usuario=`).

## Calendário (RF007)

- **Dia letivo (RN005)**: existe `DiaCalendario` com `letivo = True`. Dia ausente (fim de semana, fora do período) não é letivo. Use `core.calendario`: `eh_dia_letivo(data)`, `dias_letivos(inicio, fim)` (extremos inclusos). A regra é aplicada na hora do cálculo (RF003, RF010), nunca só na importação, porque um dia pode virar não letivo depois.
- **Ciclo (RN006)**: o que o calendário disser; sem restrição de 14 dias no banco (duração diferente gera aviso na importação e na edição). Pode haver lacunas (recesso de julho). Sobreposição é erro (`clean()`). `ciclo_em(data)` devolve o ciclo ou `None`. O número do ciclo não é armazenado: a tela numera pela ordem no ano. `data_simulado` é opcional e fica dentro do ciclo (restrição no banco).
- **Tema (RN007)**: chave na terça-feira (restrição no banco), vale de terça a segunda; terça de feriado continua tendo tema. `tema_em(data)` devolve o último tema até a data; `temas_do_ciclo(ciclo)`. `ResultadoRedacao` continua ligado por `tema_semana == TemaRedacao.data`; uma FK fica para o RF005.
- **Importação** (Diretor, `calendario/importar/`): tipos `dias` (`data`, `dia_letivo` com S/N, sim/não, 1/0; `descricao` opcional), `ciclos` (`data_inicio`, `data_fim`, `data_simulado` opcional) e `temas` (`data`, `tema`). O ano letivo é informado e linha de outro ano é inconsistente. Diferente do cadastro, reimportar **atualiza** o que mudou e audita cada campo (NF009); o que não mudou conta como sem alteração (NF008); ausente do arquivo não é tocado (NF007). Modelos para download por tipo e formato em `calendario/importar/modelo/<tipo>/<csv|xlsx>/`. A trilha (`RegistroImportacao`) ganha os tipos `CALENDARIO`, `CICLOS`, `TEMAS` e o campo `atualizados`.
- **Acesso**: qualquer autenticado lê o calendário e baixa os modelos; importar e editar é só do Diretor. Sem rota de exclusão (NF007). Não há dado pessoal.

## Suposições a confirmar

- **Áreas do simulado:** as quatro áreas do ENEM (Linguagens, Humanas, Natureza, Matemática). Confirmar com a DES como o P+ separa as áreas, sobretudo nos simulados de FUVEST.
- **Formato da matrícula:** texto de até 20 caracteres, para preservar zeros à esquerda.
