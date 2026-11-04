# Modelo de dados

Implementação física do Diagrama de Classes e do DER do Relatório Descritivo (Seções 1.4 e 1.5). Os modelos ficam em `core/models.py` e `inteligencia/models.py`.

| Modelo | Tabela do DER | Observações |
|---|---|---|
| `core.Usuario` | Usuário | Perfil Diretor ou Membro; padrão Membro (RN013) |
| `core.Turma` | Turma | Única por nome e ano letivo |
| `core.Aluno` | Aluno | Matrícula é a chave primária (RN003); `turma` é a turma atual |
| `core.HistoricoTurma` | **nova** | Períodos do aluno em cada turma (RN011) |
| `core.CicloCalendario` | Ciclo | Duas semanas entre simulados (RN006) |
| `core.RegistroFrequencia` | Frequência | Único por aluno e dia (NF008) |
| `core.ResultadoSimulado` | Simulado | Único por aluno, ciclo e área; campo `presente` (RN009) |
| `core.ResultadoRedacao` | Redação | Único por aluno e tema; competências c1 a c5 (0 a 200) |
| `core.Alerta` | Alerta | Motivo obrigatório (NF004); guarda a regra e o ciclo que o geraram |
| `core.Intervencao` | Intervenção | Ligada ao aluno e, opcionalmente, ao alerta (RF019) |
| `inteligencia.RegraAlerta` | (só no Diagrama de Classes) | Uma regra ativa por tipo; limiares no banco (RF018) |

## Garantias

- **Sem exclusão física (NF007):** todos os modelos acima, menos `Usuario`, herdam de `core.historico.HistoricoPreservado`. `delete()` gera `ExclusaoProibidaError`, tanto no objeto quanto em querysets. As chaves estrangeiras usam `PROTECT`. Um usuário de gestão anterior é desativado (`is_active = False`), não excluído.
- **Sem duplicidade (NF008):** restrições `unique` no banco para frequência, simulado, redação e turma. A importação deve usar `update_or_create` sobre essas chaves.
- **Mudança de turma (RN011):** use `aluno.mudar_turma(nova_turma, data)`. O período anterior é fechado e outro é aberto. `aluno.turma_em(data)` responde em que turma o aluno estava numa data.

## Diferenças em relação ao DER do Lab 03

Precisam de uma Solicitação de Mudança para atualizar o DER e o Relatório Descritivo:

1. **Tabela `HistoricoTurma`** (aluno, turma, início, fim). O DER guarda só a turma atual, o que não atende à RN011. Esse problema foi apontado pela revisão estática do Plano de Testes.
2. **`Intervencao.aluno`**. No DER, a intervenção se liga só ao alerta, mas o RF019 admite intervenção sem alerta.
3. **`ResultadoSimulado.presente`**. Registra a ausência no simulado, que não é avaliada em desempenho (RN009). Um ausente não tem nota (restrição no banco).
4. **`ResultadoRedacao`**: `nota_competencias` virou cinco colunas (`nota_c1` a `nota_c5`). Também foram acrescentados `entregue` (já presente no Diagrama de Classes) e `tema`. O tema é identificado pela terça-feira em que foi lançado (RN007).
5. **`Alerta.regra`, `Alerta.ciclo` e `Alerta.area`**. Registram qual regra e qual limiar geraram o alerta e a área do alerta de desempenho (RF015).
6. **`CicloCalendario` sem `temaRedacaoSemana`**. Cada ciclo tem duas semanas e, portanto, dois temas (RN007). O tema fica na redação.

## Suposições a confirmar

- **Áreas do simulado:** as quatro áreas do ENEM (Linguagens, Humanas, Natureza, Matemática). Confirmar com a DES como o P+ separa as áreas, sobretudo nos simulados de FUVEST.
- **Formato da matrícula:** texto de até 20 caracteres, para preservar zeros à esquerda.
