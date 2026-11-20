# FAROL · Guia de uso para a Direção do CASDvest

Use este guia para preparar o ano letivo, atualizar os dados e acompanhar os alunos pelo FAROL. Comece com o endereço da aplicação e uma conta de acesso fornecidos pela equipe responsável.

- Para instalar no computador da Direção, siga o [guia de instalação local](guia-instalacao-local.md).
- Para preparar o acesso da equipe, consulte o [guia de hospedagem compartilhada](guia-hospedagem-compartilhada.md).
- Para ensaiar a rotina com dados fictícios, abra o [roteiro de validação com os 12 arquivos sintéticos](guia-validacao-direcao.md#3-planilhas-e-ordem-de-carga). Ele traz a ordem de carga, os parâmetros e os resultados esperados.

Mantenha as planilhas reais na pasta restrita do Drive e envie-as pelo ambiente autorizado pelo CASDvest. Use somente exemplos sintéticos em issues, PRs e no repositório público. [Regras de uso dos dados](dominio-casd.md#7-dados-reais)

## 1. Entrar no FAROL

1. Abra o endereço da aplicação, digite seu nome de usuário e sua senha e clique em **Entrar**. Se recebeu um link de primeiro acesso, abra-o, escolha sua senha e clique em **Salvar senha** antes de entrar.
2. Confira seu nome e perfil no cabeçalho. Use **Sair** ao terminar, especialmente em um computador compartilhado.

| Perfil no cabeçalho | Acesso |
| --- | --- |
| **Diretor** | Consulta as listas nominais do painel e as fichas individuais. Gerencia cadastros, calendário, importações, pendências, regras, intervenções, auxílios e contas. |
| **Membro de diretoria** | Consulta **Painel** e **Indicadores** com dados agregados, as regras vigentes e o calendário. Também vê nomes e matrículas nas listas de cadastro de **Alunos** e **Turmas**, em modo de consulta. |

A visibilidade das listas de cadastro para o perfil **Membro de diretoria** está implementada conforme a SM #58, registrada para validação da Direção. [Perfis e acesso a dados nominais](dominio-casd.md#3-perfis-e-acesso-a-dados-nominais)

## 2. Preparar o cadastro e o calendário

### Turmas e alunos

Para cadastrar um aluno pela interface, crie primeiro a turma em **Turmas → Nova turma**, com nome e ano letivo. Depois abra **Alunos → Novo aluno** e informe matrícula, nome, **Data de ingresso** e turma. Para uma carga em lote, use **Importações → cadastro**. O FAROL pode criar as turmas que constam da planilha.

Em **Alunos**, combine **Ano letivo**, **Turma** e **Situação** e clique em **Filtrar**. Em **Turmas**, clique no nome de uma turma para ver a lista. Use **Editar** nas listas para corrigir o cadastro ou o nome de uma turma. A tela de edição mostra o histórico disponível.

- **Mudança de turma.** Em **Alunos → Editar**, selecione a nova **Turma atual**, informe a **Data da mudança de turma** e salve. O histórico na ficha mantém os vínculos anteriores e os indicadores usam a turma da data do ciclo.
- **Desligamento.** Mude **Situação** para **Desligado**, informe a **Data de saída** e salve. O cadastro continua disponível pelo filtro de situação.
- **Cadastro lançado por engano.** Use **Inválido (lançado por engano)**. A lista padrão oculta esse cadastro. O filtro **Todas, inclusive inválidos** permite consultá-lo.

### Calendário letivo

Em **Calendário**, informe o **Ano** e clique em **Ver**. Cadastre os períodos de aula antes de importar a frequência e os ciclos antes de importar os simulados. O FAROL conta de segunda a sexta dentro dos períodos letivos. Os intervalos entre os períodos representam as férias e as exceções cobrem feriados, emendas e dias extras de aula.

- **Períodos letivos.** Use **Importar planilha** para criar períodos. Para revisar um período existente, use **Editar** na lista **Períodos letivos**.
- **Exceções.** Use o link **dia** em **Novo**. Informe a data e deixe **Dia letivo** desmarcado para retirar um feriado da contagem. Marque a opção para incluir uma data extra, como um sábado com aula.
- **Ciclos.** Use o link **ciclo** em **Novo** e informe o início, o fim e a data do simulado, se houver. Use intervalos sem sobreposição. Depois que o ciclo recebe resultados, suas datas ficam fixas.
- **Temas de redação.** Use o link **tema** em **Novo** para informar a terça-feira de lançamento e o título. A importação do Corrija-me também cria o tema quando ele ainda está ausente no calendário.

Depois de salvar, confira o total de dias letivos, as exceções e as datas do ciclo. Para carregar vários itens, use os modelos de **Calendário → Importar planilha** e transcreva as datas da grade visual do curso para as tabelas correspondentes.

## 3. Importar e conferir os dados

Abra **Importações** e escolha a fonte na lista de links acima do histórico. Prepare o cadastro e o calendário primeiro. Em seguida, atualize a frequência, o resultado de cada simulado e a exportação completa de cada tema de redação. Confira o **Ano letivo** antes de cada envio.

| Fonte | Qual arquivo enviar | O que preencher no FAROL |
| --- | --- | --- |
| **cadastro** | CSV ou XLSX com **matrícula**, **nome**, **turma** e **data de ingresso**, quando disponível. Para um novo aluno, deixar o ingresso em branco define 1º de janeiro do ano informado. Preencha a data real para quem entrou depois. | Informe **Ano letivo** e **Data de mudança de turma**. A data vale para as mudanças de turma do lote. |
| **calendário** | Uma tabela por tipo, nos modelos CSV ou XLSX da tela. Use as datas do intervalo para períodos e ciclos e uma data por exceção ou tema. | Em **O que importar**, selecione **Períodos letivos**, **Dias não letivos e exceções**, **Ciclos** ou **Temas de redação**. |
| **frequência (catraca)** | Grade consolidada de presença, em planilha Excel, com **Nome**, **Matrícula** e uma coluna por data. Use **P** para presente, **F** para falta, **J** para falta justificada e **S** para sem aula. As abas diárias de passagens são insumo para preparar a grade. | Confirme **Aba da planilha**. A aba padrão é **Presença Anual**. Se usar outra grade, como **Nivelamento**, indique o nome dela. |
| **simulados (P+)** | Um relatório XLSX ou XLSM por simulado, com as abas **Resultados e Classificações TRI** e **Acertos e Porcentagens TRI**. Inclua **Matrícula** na aba de resultados. Área com nota e acertos em branco registra falta naquela etapa. | Em **Ciclo do simulado**, selecione o intervalo correspondente à avaliação. |
| **redações (Corrija-me)** | Exportação completa de um tema, com a matrícula em **RM**. Para ENEM, envie as cinco competências de 0 a 200. Para outras bancas, mantenha os critérios e a nota final da banca. Para entregas repetidas do mesmo aluno, o FAROL usa o envio mais recente. | Informe a **Terça-feira do tema**. Se a terça já tiver tema, o FAROL mantém o título cadastrado e avisa quando o título do arquivo diverge. |

O FAROL cruza as fontes pela matrícula. A matrícula do CASDvest tem sete dígitos, com dois dígitos do ano, **30** para extensivo ou **31** para semiextensivo e três dígitos sequenciais. Os arquivos de prática usam matrículas fictícias como `S268102`. Use o modelo disponível na tela de cada fonte para conferir o cabeçalho.

### Conferir e confirmar

1. Anexe o arquivo, preencha os campos da fonte e clique em **Conferir**. Em **Conferência (nada foi gravado)**, confira os registros novos, os que serão alterados, os ignorados, as linhas recusadas, os avisos e as pendências. Confira com atenção **Sobreposição de dados já existentes**.
2. Corrija a planilha ou os parâmetros quando necessário e faça uma nova conferência. As linhas válidas podem ser gravadas mesmo quando há linhas recusadas. Se o cadastro apontar divergência de nome ou ingresso, confirme o dado na fonte e corrija-o em **Alunos → Editar**. Na frequência, confira os avisos de calendário e ingresso. Nas redações, lembre-se de que os alunos ativos que não aparecem na exportação são registrados como **não entregue**.
3. Quando o resumo corresponder ao esperado, clique em **Confirmar importação**. Se o navegador perder o anexo, anexe novamente o mesmo arquivo. A conferência vale por 30 minutos. Se a tela mostrar uma nova conferência, revise o resumo atualizado antes de confirmar.
4. Confira **Importação concluída** e volte a **Importações**. O histórico mostra data e hora, usuário, arquivo, tipo, ano e contagens. Use **Usuário → Filtrar** para localizar os seus envios. Ao reenviar a mesma planilha, o FAROL compara com os dados atuais, indica os registros sem alteração e atualiza o que mudou, sem criar duplicatas.

### Resolver pendências

Frequência, simulados e redações podem trazer linhas com matrícula ausente ou sem aluno correspondente no ano. Depois de confirmar a importação, trate essas linhas em **Pendências**.

1. Filtre pelo **Ano letivo**, pela **Origem** e pela situação **Pendente**. Confira as informações da linha com a fonte e com o cadastro.
2. Se identificar o aluno, marque somente as linhas que pertencem a ele, preencha **Matrícula do aluno** e clique em **Associar selecionadas**. Se o FAROL indicar divergência de nome, verifique a identidade na fonte, marque **Confirmo que as linhas selecionadas são deste aluno** e clique novamente em **Associar selecionadas**. No roteiro sintético, por exemplo, a entrega sem RM de **Aluno Teste Brisa Exportação** corresponde à matrícula `S268102`.
3. Use **Descartar selecionadas** quando confirmar que as linhas selecionadas não correspondem a nenhum aluno. Se ainda tiver dúvida, deixe a linha pendente para revisão. Use os filtros **Associada** e **Descartada** para consultar o resultado e abra a ficha para verificar os dados aplicados.

## 4. Ler o painel, os indicadores e a ficha

### Painel

Confira o ano e as datas apresentados no **Painel**. Ele usa o ano mais recente com dados e o último ciclo com resultados de simulado como referência. Os alertas de frequência cobrem as semanas indicadas no cartão e os de desempenho cobrem o ciclo de referência. Na ausência de simulados, a situação das turmas usa a última semana de frequência disponível.

- Em **Alertas ativos**, abra **Frequência** ou **Queda de desempenho** e leia o motivo. O perfil **Diretor** pode clicar no nome do aluno para abrir a ficha. A frequência conta alertas por semana, então a mesma pessoa pode aparecer em mais de uma linha.
- Os cartões de **Presença no período** e **Redações entregues no período** resumem os dados importados. A presença inclui faltas justificadas e considera os registros de dias letivos entre o ingresso e a saída. A participação nas redações é a proporção de entregas entre os registros de tema.
- Em **Situação das turmas**, clique nas contagens para ver os alunos do recorte. **Sem presença no ciclo** indica aluno com registros de dias letivos e só faltas não justificadas no período. **Sem avaliação no ciclo** inclui quem ainda não tem uma nota TRI média anterior para comparar ou ficou sem a média atual.

### O curso em quatro grupos

Selecione **Ciclo**, escolha **Curso todo** ou uma **Turma** e clique em **Ver**. O quadro combina a presença no ciclo e a variação da nota TRI média em relação ao último simulado em que cada aluno foi avaliado. As proporções dos cartões usam o total de alunos incluídos nos quatro grupos.

| Grupo | Presença no ciclo | TRI média diante da nota anterior |
| --- | --- | --- |
| **A · Em dia** | 50% ou mais | Igual ou maior |
| **B · Nota abaixo** | 50% ou mais | Menor |
| **C · Presença abaixo** | Abaixo de 50% | Igual ou maior |
| **D · Ambas abaixo** | Abaixo de 50% | Menor |

Clique num cartão para abrir sua lista ou num ponto de **Presença × notas** para abrir a ficha. Compare a distribuição pelas barras **Grupos por turma** e pelo gráfico **Grupos ao longo do ano**. Para entrar no quadro, o aluno precisa ter frequência registrada e média no ciclo selecionado e em algum ciclo anterior. Para calcular o índice de notas, o curso precisa ter pelo menos dois deltas diferentes no ciclo. No ciclo 2 do roteiro, por exemplo, Duna fica no grupo **D** com presença de 0% e queda de 10 pontos, e aparece como **Estagnado** na situação das turmas com o limiar de 30 pontos.

### Indicadores e ficha

Em **Indicadores**, use os filtros **Turma**, **Área** e **Ciclo (detalhe)** e clique em **Filtrar**. Use **Média das quatro áreas** para comparar a TRI geral ou selecione Linguagens, Humanas, Natureza ou Matemática para analisar uma área. O detalhe do ciclo mostra a quantidade de avaliados, nota média, presença, redações entregues, quedas e evoluções. Os gráficos e a tabela **Evolução no tempo** mostram a série de ciclos do recorte.

Abra a **Ficha** por **Alunos**, por uma lista nominal do painel ou pelo gráfico dos grupos. Ela reúne turma, ingresso e situação, trajetória nos grupos, **Evolução das notas**, **Frequência por ciclo**, **Alertas**, **Intervenções**, **Redações** e histórico de **Turmas**. O delta **Δ** compara a nota atual com a última nota disponível do próprio aluno. A média da turma serve de referência. A média individual exige nota nas quatro áreas. O primeiro simulado pode ter notas válidas com o delta em branco.

## 5. Tratar alertas e faltas

Use o motivo do alerta e os dados da ficha para decidir se cabe conversar com o aluno. Os alertas são indicativos e o acompanhamento é registrado pela Direção.

- **Frequência.** A regra começa em **3 faltas não justificadas na semana**, de segunda a domingo. O alerta é gerado quando o número de faltas atinge o limiar vigente.
- **Queda de desempenho.** A regra começa em **30 pontos TRI**. Uma queda a partir do limiar na média das quatro áreas ou em uma área avaliada pode sinalizar o aluno no ciclo. Na tabela **Situação das turmas**, as categorias de desempenho seguem a variação da média das quatro áreas.

### Aprovar ou retirar uma justificativa

1. Abra a ficha e clique em **Faltas e justificativas**. Localize a data e clique em **Justificar** para aprovar a justificativa. Para desfazer a aprovação, use **Retirar justificativa**.
2. Confira a situação da falta, a frequência na ficha e a lista de alertas. A falta justificada conta como presença e pode fazer o alerta semanal deixar de valer. A ficha preserva o alerta corrigido no histórico. Reenviar a grade com **F** na data preserva a justificativa já registrada.

### Ajustar o limiar de alerta

1. Abra **Regras → Alterar o limiar**, na regra que deseja ajustar. Informe um número inteiro de 1 a 7 para frequência ou um valor de 1 a 500 pontos para desempenho.
2. Clique em **Pré-visualizar** e compare quantos alunos seriam sinalizados pelo valor atual e pelo proposto. A prévia conta pessoas. O cartão de frequência conta ocorrências semanais.
3. Clique em **Salvar este limiar** para confirmar o valor pré-visualizado. O FAROL recalcula os alertas do ano de referência. Em **Regras**, consulte **Limiares anteriores** e abra a edição para ver o histórico disponível com data, autor e valores.

## 6. Registrar intervenções e desfechos

1. Na ficha, clique em **Registrar intervenção** junto ao alerta para preencher **Alerta de origem (opcional)**. Para iniciar um acompanhamento sem vincular um alerta, use **Registrar intervenção** na seção **Intervenções** da mesma ficha.
2. Selecione **Contato**, **Conversa**, **Encaminhamento** ou **Outro**. Informe a data, a pessoa responsável e uma descrição do que foi feito. Se ainda estiver aguardando um retorno, deixe o desfecho em branco. Clique em **Registrar**.
3. Quando houver desfecho, use **Registrar desfecho** ou **Atualizar desfecho** na ficha. Escolha **Resolvido**, **Em acompanhamento** ou **Sem retorno** e clique em **Salvar desfecho**.
4. No menu **Intervenções**, consulte o histórico pelo nome ou matrícula, tipo, desfecho e intervalo de datas. Use **Pendente (sem desfecho)** para localizar ações que ainda precisam de atualização.

## 7. Gerar o relatório de auxílios

Antes de usar uma lista real, confirme com a Direção se o consentimento da matrícula cobre esse uso. [Uso dos dados de auxílios](dominio-casd.md#alunos-beneficiados-por-auxílios-rf021-sm-80)

1. Em **Auxílios**, anexe uma planilha com uma única coluna **matrícula**, informe o **Ano letivo** e clique em **Gerar relatório**. Os modelos da tela estão disponíveis em XLSX e CSV.
2. Confira as contagens de matrículas válidas, encontradas, sem aluno correspondente e linhas recusadas. O **Resumo para a prestação de contas** compara beneficiados e demais alunos em frequência, redações, desempenho, alertas e intervenções. Use apenas esse bloco agregado na prestação de contas.
3. Use a **Lista nominal** na sessão de **Diretor** para verificar os alunos encontrados. O FAROL usa o arquivo em memória durante a consulta. Matrículas sem correspondência aparecem apenas na contagem e o envio fica fora do histórico de **Importações** e **Pendências**. Para gerar outro relatório, anexe a lista novamente.

## 8. Gerenciar contas e acompanhar o fechamento do ciclo

### Criar, redefinir ou revogar acesso

1. Abra **Usuários → Novo usuário**, informe os dados da conta, inclusive o e-mail, escolha o **Perfil** e clique em **Salvar**. Na edição da conta, clique em **Gerar link para definir senha**.
2. Copie o link antes de sair da tela e encaminhe-o à pessoa por um canal privado. A tela exibe o link uma vez. Ele expira e serve para definir a senha uma única vez. Ao gerar um link de redefinição para uma conta existente, a senha anterior perde a validade imediatamente.
3. Para alterar o perfil ou o e-mail, abra **Usuários → Editar**. Para revogar o acesso, desmarque **Acesso ativo** e salve. Para reativar, marque a opção novamente. Consulte **Histórico de alterações** na edição. Para a troca de gestão, mantenha pelo menos uma conta **Diretor** ativa antes de revogar ou mudar o perfil de outra.

A gestão das contas comuns fica em **Usuários**. A conta técnica criada na instalação é gerida pela equipe responsável pelo ambiente.

### E-mail de fechamento de ciclo

Ao fechar um ciclo, conclua os envios de frequência, do simulado e das redações e resolva as pendências confirmadas. Confira previamente o e-mail e **Acesso ativo** nas contas da equipe. O resumo é enviado a contas comuns ativas com e-mail, dos perfis **Diretor** e **Membro de diretoria**. A conta técnica de instalação fica fora dos destinatários.

O envio depende da execução configurada pela equipe técnica. Ele considera o ciclo encerrado mais recente com resultados de simulado e, na rotina normal, envia uma vez por ciclo. A mensagem traz datas, números agregados do curso e por turma e, quando o endereço do FAROL foi configurado, um link para o painel. Se ela não chegar, confirme o fechamento, a importação das notas, o e-mail da conta e a caixa de spam. A equipe técnica pode conferir a execução do envio. [Teste local do e-mail de fechamento](guia-validacao-direcao.md#11-e-mail-de-fechamento-de-ciclo)

## 9. Resolver problemas comuns

| O que aparece | O que conferir |
| --- | --- |
| **Entrada bloqueada** | Aguarde o fim do bloqueio e tente entrar novamente. Na configuração inicial, o bloqueio dura 15 minutos após 5 tentativas incorretas. |
| **Link inválido** ao definir senha | Peça à Direção um novo link e confirme que a conta está ativa. |
| **Acesso negado** ou link ausente no menu | Verifique o perfil no cabeçalho. Para tarefas de edição e acompanhamento individual, use uma conta **Diretor** autorizada. |
| **Sem dados no período** | Confira o ano em **Painel** e o status do envio em **Importações**. Cadastro e calendário preparam a base. O painel usa frequência ou resultados de simulado para mostrar o período. Para consultar outro ano, acrescente `?ano=2026` ao endereço do painel, substituindo 2026 pelo ano desejado. |
| Arquivo recusado ou linha inconsistente | Confira a extensão, o cabeçalho, a aba e o ano conforme o modelo da fonte. Corrija a linha indicada e volte a **Conferir**. |
| Muitas linhas em **Pendências** | Confira se o cadastro do mesmo ano foi importado e se a matrícula foi preenchida em **Matrícula** ou **RM**, conforme a fonte. |
| Frequência menor que a esperada | Compare as datas da grade com **Calendário** e consulte a ficha para conferir ingresso, saída e justificativas. Se corrigir o calendário para incluir um dia que ficou de fora da importação, confira e confirme novamente a grade. |
| Nota média, delta ou grupo ausente | Confira o ciclo escolhido, a frequência, as notas das quatro áreas, a existência de uma média anterior e os dados dos demais avaliados no ciclo. |

Se precisar de ajuda, informe à equipe a tela, o perfil, o ano, o horário e a mensagem exibida. Use a base sintética para reproduzir um caso em canais públicos.
