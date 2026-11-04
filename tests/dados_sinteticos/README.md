# Base sintética de teste

Dados **inventados** para desenvolvimento e testes (NF017). Nenhum dado real de aluno é usado, nem como inspiração. Os nomes são combinações aleatórias de listas genéricas e as matrículas começam com `S`, formato que o CASD não usa.

Gerada por [`scripts/gerar_base_sintetica.py`](../../scripts/gerar_base_sintetica.py) com semente fixa, então rodar de novo produz exatamente os mesmos arquivos:

```bash
uv run python scripts/gerar_base_sintetica.py                     # pequena/ (versionada)
uv run python scripts/gerar_base_sintetica.py --tamanho completa  # completa/ (não versionada)
uv run python scripts/gerar_base_sintetica.py --semente 7 --destino /tmp/outra
```

| Tamanho | Alunos | Turmas | Anos letivos | Uso |
|---|---|---|---|---|
| `pequena` | 20 por ano (60 no total) | 5 | 2024, 2025, 2026 | Testes automatizados; versionada |
| `completa` | 500 por ano (1.500 no total) | 5 | 2024, 2025, 2026 | Teste de carga (NF010–NF012); cerca de 18 MB, gerada sob demanda |

Se mudar o gerador, regere a base `pequena` e versione o resultado. O teste `test_base_versionada_corresponde_ao_gerador` falha se as duas divergirem.

## Calendário simulado

- Ano letivo da primeira segunda-feira a partir de 2/2 até a última sexta-feira até 27/11, **de segunda a sexta**.
- Feriados nacionais e de São José dos Campos (19/3 e 27/7), mais Carnaval, Sexta-feira Santa e Corpus Christi (RN005).
- Recesso de duas semanas a partir da primeira segunda-feira de julho.
- Ciclos de duas semanas, de segunda a domingo, com o simulado no domingo que fecha o ciclo (RN006).
- Tema novo de redação toda terça-feira, fora do recesso (RN007).
- Três chamadas de matrícula: início do ano, 5 e 10 semanas depois (RN004).

Essas são **suposições** para a base sintética. Confirmar com a Direção os dias de aula do CASDvest, que também tem atividades nos fins de semana, e o dia dos simulados.

## Formato dos arquivos

Uma pasta por ano letivo (`pequena/2026/`...). Todos os arquivos são CSV em UTF-8, com separador `;`, datas `dd/mm/aaaa` e decimal com vírgula, como nas planilhas em português.

> Os formatos reais das exportações da catraca, do P+ e do Corrija-me ainda não foram vistos. Estes são **plausíveis**, baseados na ata da 1ª reunião, e devem ser ajustados quando as amostras chegarem à pasta restrita do Drive.

| Arquivo | Origem simulada | Colunas | Uma linha por |
|---|---|---|---|
| `cadastro_alunos.csv` | Planilha "Banco de Dados – CASDvest" | `matricula`, `nome`, `turma` (atual), `data_ingresso` | aluno |
| `historico_turmas.csv` | Cadastro | `matricula`, `turma`, `data_inicio`, `data_fim` (vazio = atual) | período do aluno numa turma (RN011) |
| `calendario_letivo.csv` | Planilha do Poliedro | `data`, `dia_letivo` (`S`/`N`), `descricao` (feriado ou recesso) | dia útil do ano letivo |
| `ciclos.csv` | Planilha do Poliedro | `ciclo`, `data_inicio`, `data_fim`, `data_simulado` | ciclo |
| `temas_redacao.csv` | Corrija-me | `data`, `tema` | terça-feira |
| `catraca_presencas.csv` | Catraca (Google Script) | `data`, `matricula`, `nome` | **passagem**: falta é a ausência de linha (RN001) |
| `justificativas.csv` | RH | `data`, `matricula`, `aprovada` | ausência justificada (RN002) |
| `p_mais_simulados.csv` | P+ | `simulado`, `data`, `matricula`, `nome`, `presenca` (`Presente`/`Ausente`) e, por área (`LC`, `CH`, `CN`, `MT`), `<area>_acertos` (0–45) e `<area>_tri` | aluno e simulado; ausente tem as notas vazias |
| `corrija_me_redacoes.csv` | Corrija-me | `data_tema`, `tema`, `matricula`, `nome`, `entregue` (`S`/`N`), `c1`–`c5` (0–200), `total` | aluno e tema; não entregue tem as notas vazias |

## Perfis com resultado conhecido

Ficam no último ano (2026), nos primeiros alunos da Turma A e da Turma B. As matrículas e o resultado esperado de cada um estão em `perfis_conhecidos.json`, que os testes leem em vez de repetir os valores.

| Perfil | O que acontece | Regra |
|---|---|---|
| `tres_faltas_na_semana` | Presente o ano todo, exceto segunda, terça e quarta de uma semana, sem justificativa | RN001, RF014 |
| `falta_justificada` | Mesmas três ausências, mas a de quarta é justificada: só duas faltas | RN002 |
| `ausente_no_simulado` | Ausente no simulado do ciclo 6; nota 600 nos demais | RN009 |
| `mudou_de_turma` | Turma A → Turma B no meio do ano | RN011 |
| `segunda_chamada` | Ingressa na segunda chamada, sem registros antes disso | RN004 |
| `queda_de_desempenho` | TRI 650 até o ciclo 7 e 590 a partir do ciclo 8 (Δ = −60) | RN008, RF015 |
| `evolucao_consistente` | TRI sobe 15 pontos por ciclo | RF016 |

Os demais alunos têm comportamento aleatório, mas reproduzível. Qualquer um deles pode, por acaso, atingir um limiar de alerta. Os testes devem verificar os perfis conhecidos, e não contar quantos alunos foram sinalizados.

## Inconsistências conhecidas (NF006)

Também listadas em `perfis_conhecidos.json`, para testar a importação tolerante a falhas:

- `matricula_desconhecida`: uma passagem na catraca com matrícula que não está no cadastro (`S999999`).
- `matricula_em_branco`: uma redação no Corrija-me sem matrícula. A revisão estática encontrou esse caso no export real.
