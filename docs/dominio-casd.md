# Domínio do CASD: fatos confirmados

Fatos sobre o funcionamento do CASDvest que o código do FAROL precisa respeitar e que não estão (ou ainda não estão) no Documento de Requisitos. Cada item diz quem confirmou, quando e onde a decisão foi registrada.

> ⚠️ **Repositório público.** Este documento descreve regras e formatos, nunca dados reais. Não acrescente nomes de alunos, professores, palestrantes ou membros da gestão, nem trechos de planilhas reais.

Quando um fato daqui mudar um requisito, ele precisa de uma Solicitação de Mudança (SM) e de atualização do Documento de Requisitos no Drive. Não basta decidir no PR.

## 1. O curso

- **Escopo da v1:** só o CASDvest. O CASDinho fica fora.
- **Modalidades:** o CASDvest tem duas, o **extensivo** e o **semiextensivo** (alunos do 2º ano do ensino médio). O semiextensivo começa mais tarde, em maio.
- **Capacidade:** no máximo 900 alunos por ano.
- **Gestão:** o curso é gerido por alunos do ITA, e por isso o calendário interno segue a referência das semanas do ITA (seção 4).

## 2. Matrícula

*Confirmado pela equipe em 16/11/2026 (revisão do PR #57).*

| Parte | Valor | Exemplo (2026) |
|---|---|---|
| Ano | dois últimos dígitos do ano letivo | `26` |
| Modalidade | `30` extensivo · `31` semiextensivo | `2630xxx` · `2631xxx` |
| Sequencial | sempre 3 dígitos | `2630042` |

- São sempre 7 dígitos.
- **O aluno recebe uma matrícula nova a cada ano.** Não há vínculo entre as matrículas de anos diferentes. Como o prefixo muda com o ano, os números nunca se repetem entre anos, então a matrícula sozinha é a chave do aluno (RN003).
- **Zeros à esquerda não ocorrem**, porque a matrícula começa pelo ano.
- **Validação:** `ingestao.cadastro.validar_matricula(matricula, ano)` recusa matrícula fora do padrão ou de outro ano letivo. Uma matrícula de outro ano nunca deve mudar um aluno de turma.
- **Base sintética:** usa de propósito o formato `S` + `AA` + 4 dígitos (`S260001`), que o CASD não usa, para que um dado sintético nunca coincida com um real (NF017). A validação aceita os dois formatos e confere o ano em ambos.
- **A modalidade pode ser derivada da matrícula** (`30`/`31`), o que pode servir aos indicadores agregados (RF012).

## 3. Perfis e acesso a dados nominais

| Perfil | Pode |
|---|---|
| **Diretor** | Tudo: dados nominais, importações, cadastro e edição, gestão de usuários. |
| **Membro de diretoria** | Indicadores agregados e as **listas de cadastro com nomes** (alunos e turmas). Não importa, não cria e não edita. |

- A visibilidade dos nomes ao Membro altera a RN013/NF013 e está registrada na **SM #58** (decisão da equipe em 16/11/2026, aguardando validação da Direção do CASD).
- Continuam **só do Diretor**: ficha longitudinal (RF011), alertas por aluno (RF010), intervenções (RF019, RF020) e todas as importações (RF003 a RF007).
- Em código, rota com dado nominal ou escrita usa `@diretor_required` (`web/acesso.py`).

### Alunos beneficiados por auxílios (RF021, SM #80)

- **Origem do dado:** nenhum documento do CASD define de onde vem a lista de beneficiados, e ser beneficiado é dado socioeconômico (fora do escopo, FAROL_Contexto, "não fará"). Pela **SM #80, opção A**, o Diretor envia a lista a cada uso, numa planilha só com matrículas, e o sistema a usa só em memória. **Nunca** se guarda a lista, o tipo de auxílio ou o fato de o aluno ser beneficiado.
- **Exceção à regra de pendências:** matrícula do arquivo sem aluno no cadastro **não** vira `PendenciaImportacao` (gravá-la seria gravar o fato socioeconômico); aparece só como contagem. Nada é auditado, porque nada é alterado.
- **Premissa a confirmar com a Direção do CASD:** o termo de consentimento (RN014) cobre esse uso. O relatório não deve ser usado antes dessa confirmação.
- **Relatório:** o bloco agregado (sem nome nem matrícula) é o que vai para a prestação de contas; a lista nominal é separada e só do Diretor (RN013).

## 4. Calendário

*Confirmado pela equipe em 16/11/2026 (revisão do PR #63).*

- **Dias de aula:** o extensivo e o semiextensivo têm aula de **segunda a sexta**.
- **Não letivos:** feriados, emendas e férias (RN005). As férias do meio do ano ficam em julho.
- **Dia letivo, como está implementado (PR #63):**
  - é letivo o dia de **segunda a sexta dentro de um `PeriodoLetivo`**, desde que não exista `DiaCalendario(letivo=False)` naquela data (feriado ou emenda);
  - um `DiaCalendario(letivo=True)` é a exceção contrária (por exemplo, um sábado com aula) e conta por si;
  - as férias são o intervalo entre dois períodos.

  O Diretor cadastra só os períodos (alguns por ano) e as exceções (15 a 20 por ano). Use sempre `core.calendario.eh_dia_letivo` e `dias_letivos` na hora do cálculo. A alternativa, listar cada dia letivo, foi descartada: um dia esquecido apagaria faltas sem aviso no RF003.
- **Tema de redação vigente:** `core.calendario.tema_em(data)` devolve o tema da terça anterior (janela de 7 dias), ou `None` na semana sem tema.
- **Ciclo de desempenho (RN006):** as duas semanas entre simulados. Os simulados do CASD aparecem no calendário interno com nomes variados (por exemplo, "ENEM 1 CASD", "Simulado Nivelamento").
- **Datas dos ciclos são fixas** e definidas no início do ano (confirmado pela equipe em 16/11/2026, ao decidir a pendência da #15). Por isso, ciclo que já tem resultado de simulado não muda de data, nem pela tela nem pela importação do calendário (RF004).
- **Semanas do ITA:** o calendário interno numera as semanas pelo calendário do ITA ("1ª" a "8ª" e "semaninha"). Na **semaninha**, o CASD continua com aulas normais (salvo férias ou feriado), mas os alunos do ITA folgam e o efetivo da gestão diminui. Isso **não** muda o que é dia letivo nem os ciclos. A referência é tratada na #64.

### A planilha do calendário interno

- É uma **grade visual**, mês a mês: dois meses lado a lado; em cada semana, uma linha com os números dos dias e, abaixo, uma linha com os eventos; categorias por cor, com legenda (RH, ENS, DES, "Feriado ou Emenda", Palestras).
- É **atualizada continuamente** ao longo do ano.
- **Não serve como fonte direta de importação:**
  - a cor de feriado nem sempre é aplicada;
  - os nomes dos eventos variam;
  - o nome da aba não diz o ano com segurança;
  - há vestibulares e eventos externos misturados;
  - o texto dos eventos contém **nomes de pessoas**.
- Uma eventual leitura automática da grade é melhoria futura. Ela precisa passar pela etapa de conferir e ignorar o texto livre.
- **Nunca versionar** essa planilha nem trechos dela.

## 5. Redação

- **Temas (RN007):** um tema novo toda terça-feira, publicado manualmente no **Corrija-me** pelo membro de redações, junto com os professores de redação. Os temas não estão na planilha do calendário.
- A importação do RF005 (#16) cria o `TemaRedacao` da terça a partir da exportação do Corrija-me, quando ainda não existe; se já existe, mantém o cadastrado e avisa se o título difere. O cadastro manual serve para corrigir ou antecipar.

## 6. Planilhas do dia a dia

*Amostras entregues pela equipe em 16/11/2026 (#74). Os arquivos têm nomes e e-mails de alunos e ficam só na pasta restrita do Drive; aqui vai só o layout. Réplicas sintéticas: `tests/dados_sinteticos/pequena/2026/planilhas/`.*

- **Matrícula (RN003 mantida):** nenhuma das planilhas trazia a matrícula. A equipe decidiu manter a associação pela matrícula e acrescentar a coluna `Matrícula` à grade de presença e ao relatório do P+; no Corrija-me, a matrícula vai na coluna `RM`, que já existe e vinha vazia.
- **Catraca e grade de presença** (`Controle de Presença AAAA.xlsx`):
  - a catraca gera uma aba por dia com `NOME` e a hora de chegada (vazio = não passou); a equipe monta com `PROCV` pelo nome a grade "Presença Anual" (e "Nivelamento", no início do ano);
  - a grade tem uma linha de título, uma de "Semana N" e o cabeçalho `Nome`, `Turma`, `% Presença`, `Faltas totais` e uma coluna por dia útil, agrupadas por semana com uma coluna `Faltas`;
  - códigos: `P` presente, `F` falta (sem passagem), `J` falta justificada, `S` sem aula (feriado, recesso ou antes do início do semiextensivo); a `Turma` vira "Desligado" quando o aluno sai;
  - as abas "Chegada" pontuam o horário (de 5, até 18h15, a 1, até 21h50); a pontualidade não é requisito do FAROL hoje (RN001 não tem tolerância de atraso);
  - o FAROL importa a grade (decisão da equipe em 16/11/2026), não as abas diárias.
- **Relatório do P+** (`.xlsm`, uma avaliação por arquivo): abas "Resultados e Classificações TRI" (nota TRI e posições por área e etapa) e "Acertos e Porcentagens TRI" (questões, acertos e porcentagem por área), com `ID Aluno`, `Inscrição`, `E-mail p4ed`, `Nome Aluno` e `Turma` ("CASDvest AAAA - Turma N"). Sem data: o nome da avaliação é do tipo "4º Simulado Enem". Etapa 1 = Linguagens e Humanas; Etapa 2 = Natureza e Matemática; área em branco = falta naquela etapa.
- **Exportação do Corrija-me** (aba `Worksheet`): uma linha por redação **entregue**, com `ID DA REDACAO`, `ID DA ATIVIDADE`, `DATA ENVIO`, `DATA CORREÇÃO`, `NOME COMPLETO`, `EMAIL`, `RM`, `BANCA`, `TEMA`, `C1`–`C5`, `NOTAL FINAL` (sic) e dados de turma. Não traz a data de lançamento do tema. Na amostra (CASDinho), a banca é VUNESP: quatro critérios, notas decimais e nota final de 0 a 100; no CASDvest, espera-se a banca ENEM (cinco competências de 0 a 200).
- **Outras planilhas da amostra** (controle de presença de redação, dashboard de redação, protótipo antigo) são derivadas ou de acompanhamento e não são fontes de importação. A aba de contato com alunos inativos traz apelidos da gestão e resumos de conversa: nunca copiar.

## 7. Dados reais

- Planilhas e exportações reais (catraca, P+, Corrija-me, cadastro, calendário) ficam só na **pasta restrita do Drive**. Nunca no Git, em issues, PRs ou comentários.
- Desenvolvimento e testes usam só a base sintética em `tests/dados_sinteticos/` (NF017).
- Para descrever o layout de uma planilha real numa issue ou PR, use só o cabeçalho e linhas inventadas.

## 8. Onde cada decisão está registrada

| Assunto | Registro |
|---|---|
| Membro vê nomes nas listas de cadastro; importar é só do Diretor | SM #58 |
| Formato da matrícula | Comentário de revisão no PR #57; este documento |
| Modelo de dia letivo, aulas de segunda a sexta | Revisão e implementação no PR #63 |
| Datas de ciclo fixas; ciclo com resultados não muda de data | Equipe, 16/11/2026 (#15); implementado no RF004 |
| Semanas do ITA | #64 |
| Fonte dos temas de redação | Comentário na #16 |
| Aviso de passagens em dia não letivo no RF003 | Comentário na #14 |
| Layouts das planilhas reais; matrícula acrescentada; fonte da frequência; tema escolhido pelo Diretor | #74 |
