# FAROL · Guia de uso e validação para a Direção do CASDvest

Este roteiro detalhado acompanha a validação do FAROL pela Direção, da carga inicial de dados ao registro de um acompanhamento individual. Cada etapa traz o que fazer e o que conferir na tela.

## 1. Baixar e rodar o FAROL no seu computador

Use apenas dados fictícios nesta instalação local de teste.

### Baixar os arquivos do GitHub

1. Abra o repositório do FAROL e selecione a versão indicada pela equipe no seletor de branches, acima da lista de arquivos. Se a equipe indicar a versão principal, selecione **main**. [Repositório FAROL no GitHub](https://github.com/Victor-9882/FAROL)
2. Clique em **Code → Download ZIP**. Quando o download terminar, extraia o ZIP. Abra a pasta extraída que contém `manage.py`, `docker-compose.yml` e `.env.example`. É nessa pasta que você vai executar os comandos. [Instruções de download do GitHub](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives)
3. Dentro da pasta extraída, abra `tests/dados_sinteticos/validacao_direcao/` e confira se estão lá os 12 arquivos numerados de **01** a **12**. No momento do upload, selecione os arquivos dessa pasta. Se ela não aparecer no ZIP, peça à equipe a versão que inclui as planilhas ou use os arquivos de teste que ela enviou junto com o guia.

### Preparar a configuração local

Abra um terminal na pasta extraída. No Windows, abra a pasta no Explorador de Arquivos, digite `powershell` na barra de endereços e pressione Enter. No macOS ou Linux, abra o Terminal, digite `cd` seguido de um espaço, arraste a pasta extraída para a janela e pressione Enter.

Na primeira instalação, copie o arquivo de configuração de exemplo para `.env`. Execute o comando do seu sistema.

**Windows (PowerShell)**

```powershell
Copy-Item .env.example .env
```

**macOS ou Linux**

```bash
cp .env.example .env
```

Abra `.env` em um editor de texto. No Windows, você pode usar `notepad .env` no PowerShell. No macOS, use `open -e .env` no Terminal. Na linha `DJANGO_SECRET_KEY=`, substitua o valor de exemplo por uma sequência longa e aleatória para esta instalação. Mantenha `DJANGO_DEBUG=True` para o acesso por HTTP local. Acrescente esta linha ao fim do arquivo para que o link no e-mail de teste aponte para o seu FAROL.

```dotenv
SITE_URL=http://localhost:8000
```

Salve com o nome `.env` e mantenha o arquivo no seu computador.

### Iniciar com Docker Compose

1. Instale e abra o **Docker Desktop**. No Linux, se você já usa Docker Engine, verifique se o plugin **Docker Compose** está instalado. De volta ao terminal da pasta do FAROL, execute `docker compose version`. O comando deve mostrar a versão do Compose. [Instalação oficial do Docker Compose](https://docs.docker.com/compose/install/)
2. Com o Docker em execução, rode o comando abaixo. Na primeira vez, deixe o computador conectado à internet enquanto o Docker baixa as dependências, prepara o banco e inicia o FAROL.

   ```bash
   docker compose up -d --build --wait
   ```

3. Abra [a página de verificação local](http://localhost:8000/saude/) no navegador. Ela deve mostrar `{"status": "ok"}`. Para verificar os serviços, use `docker compose ps`. Se o FAROL não iniciar, anote a mensagem do terminal e use `docker compose logs --tail=80 app` para consultar o erro. Se a mensagem indicar que não foi possível conectar ao Docker, confira se o Docker Desktop ou o Docker Engine está em execução.
4. Crie a primeira conta na mesma janela do terminal. Escolha nome de usuário, e-mail e senha quando o comando pedir. É normal a senha não aparecer enquanto você digita. O FAROL cria essa conta com o perfil **Diretor**.

   ```bash
   docker compose exec app python manage.py createsuperuser
   ```

Quando terminar a sessão de teste, pare os serviços com `docker compose stop`. Para voltar, abra o terminal **na mesma pasta** e rode `docker compose up -d --wait`. A conta e os dados importados ficam no banco local entre as sessões. Use a [caixa de e-mail local do Mailpit](http://localhost:8025/) na seção 11.

### Iniciar sem Docker com uv e SQLite

Se o computador não puder usar Docker, instale o **uv** para o seu sistema e reabra o terminal. No mesmo arquivo `.env` criado acima, altere as linhas de **banco de dados** e **e-mail** para estes valores. [Instalação oficial do uv](https://docs.astral.sh/uv/getting-started/installation/)

```dotenv
DATABASE_URL=sqlite:///db.sqlite3
EMAIL_URL=consolemail://
```

Na pasta do FAROL, execute um comando de cada vez. O uv instala o Python 3.12 se ele estiver faltando e prepara as dependências do projeto. O comando `createsuperuser` pede os dados da primeira conta **Diretor**.

```bash
uv sync --locked --python 3.12 --no-dev
uv run --locked --no-dev python manage.py migrate
uv run --locked --no-dev python manage.py createsuperuser
uv run --locked --no-dev python manage.py runserver 127.0.0.1:8000
```

Confira a [página de verificação local](http://localhost:8000/saude/). Mantenha o terminal aberto enquanto usa o FAROL. Para parar, pressione **Ctrl+C**. Para voltar, execute novamente só o comando `runserver` acima, na mesma pasta. A conta e os dados ficam no arquivo `db.sqlite3`.

### Primeiro acesso

Abra o [FAROL no seu computador](http://localhost:8000/) e entre com a conta que acabou de criar. Confira se o cabeçalho mostra seu nome de usuário e o perfil **Diretor**. Antes da carga, o **Painel** deve mostrar **Sem dados no período**. Clique em **Sair**, tente abrir novamente o painel para conferir o retorno à tela de entrada e entre de novo.

- Para reproduzir os números do guia, comece com uma base sem dados de 2026 e confira em **Regras** se os limiares iniciais são **3 faltas semanais** e **30 pontos de queda na TRI**.
- Use uma janela normal para a conta Diretora e uma janela privativa para testar a conta de Membro. Reserve outra sessão se também for testar o bloqueio de login.
- Registre os resultados na lista ao fim do guia e use apenas dados fictícios nas evidências que entregar à equipe.

## 2. Como conferir e confirmar uma importação

1. Abra **Importações** e escolha a fonte no alto da página. Anexe o arquivo e preencha os parâmetros pedidos.
2. Clique em **Conferir**. A tela mostra **Conferência (nada foi gravado)** e informa quantos registros serão criados, atualizados, ignorados ou recusados. Leia os avisos e as pendências. Você pode abrir **Importações** em outra aba e verificar que ainda não há uma linha nova no histórico.
3. Se o resumo estiver de acordo com o esperado, clique em **Confirmar importação** e confira o título **Importação concluída**. Se o navegador tiver perdido o anexo, selecione o mesmo arquivo novamente. Com JavaScript habilitado, mudar arquivo ou parâmetro limpa a conferência. Se o sistema oferecer um novo resumo após a confirmação, confira-o antes de prosseguir. A conferência expira em 30 minutos.
4. Volte a **Importações**. Confira a linha com data e hora, usuário, nome do arquivo, tipo, ano e contagens. Teste **Filtrar** com seu nome de usuário. A trilha guarda os metadados do envio e as contagens.

**Como ler o resumo.** Um aviso aponta algo a conferir na fonte ou no calendário. Uma linha inconsistente foi recusada e pode ser corrigida na planilha. Uma divergência no cadastro pede revisão manual. Uma pendência de frequência, simulado ou redação guarda a linha para associação manual pela Direção. Uma importação pode gravar as linhas válidas mesmo quando há linhas recusadas.

Para testar a proteção contra duplicação, confira e confirme novamente o **mesmo** arquivo de cadastro antes de avançar. Na segunda passagem, espere **5 sem alteração**, **0 novos** e a mesma linha recusada. Cada confirmação tem sua própria entrada na trilha de importações.

## 3. Planilhas e ordem de carga

No seletor de arquivos do FAROL, abra a pasta `tests/dados_sinteticos/validacao_direcao/` que veio no ZIP. Os links abaixo também abrem os exemplos quando você consulta este guia no GitHub. Use **Ano letivo = 2026** em todos os envios, inclusive em **Auxílios**. A carga inicial vai do arquivo **01** ao **10**. Guarde **11** para o relatório de auxílios e **12** para a revisão do cadastro.

| Arquivo | Onde usar | O que conferir na primeira importação |
| --- | --- | --- |
| [01 · Cadastro de alunos](../tests/dados_sinteticos/validacao_direcao/01_cadastro.xlsx) | **Importações → cadastro**, com **Data de mudança de turma = 02/02/2026** | 5 alunos e 2 turmas criados. Uma linha recusada por matrícula de outro ano. |
| [02 · Período letivo](../tests/dados_sinteticos/validacao_direcao/02_periodos.csv) | **Importações → calendário**, opção **Períodos letivos** | 1 período, de 02/02 a 27/02. |
| [03 · Exceções do calendário](../tests/dados_sinteticos/validacao_direcao/03_excecoes.csv) | **Importações → calendário**, opção **Dias não letivos e exceções** | 2 exceções. Em 18/02 não há aula. Sábado, 21/02, tem aula. |
| [04 · Ciclos e simulados](../tests/dados_sinteticos/validacao_direcao/04_ciclos.csv) | **Importações → calendário**, opção **Ciclos** | 2 ciclos. O primeiro vai de 02/02 a 15/02, com simulado em 15/02. O segundo vai de 16/02 a 01/03, com simulado em 01/03. |
| [05 · Tema de redação](../tests/dados_sinteticos/validacao_direcao/05_temas.csv) | **Importações → calendário**, opção **Temas de redação** | 1 tema em 17/02, **Acesso a espaços de leitura**. |
| [06 · Grade de frequência](../tests/dados_sinteticos/validacao_direcao/06_presenca_anual.xlsx) | **Importações → frequência (catraca)**, com **Aba da planilha = Presença Anual** | 20 dias letivos e 84 registros criados, com 64 presenças, 19 faltas e 1 justificada. Há 1 pendência e avisos sobre 18/02 e um registro anterior ao ingresso. |
| [07 · P+ do ciclo 1](../tests/dados_sinteticos/validacao_direcao/07_pmais_ciclo_1.xlsx) | **Importações → simulados (P+)**. Selecione o ciclo de **02/02/2026 a 15/02/2026**. | 4 alunos com resultado novo. Se abrir o painel agora, o ciclo ainda está sem grupos, pois é o primeiro simulado. |
| [08 · P+ do ciclo 2](../tests/dados_sinteticos/validacao_direcao/08_pmais_ciclo_2.xlsx) | **Importações → simulados (P+)**. Selecione o ciclo de **16/02/2026 a 01/03/2026**. | 5 alunos com resultado novo, 1 ausência parcial e 1 pendência. |
| [09 · Corrija-me de 17/02](../tests/dados_sinteticos/validacao_direcao/09_corrija_me_17-02.xlsx) | **Importações → redações (Corrija-me)**, com **Terça-feira do tema = 17/02/2026** | 1 entrega nova, 3 registros de não entrega e 1 pendência por RM em branco. O tema, já cadastrado pelo arquivo 05, é usado. |
| [10 · Corrija-me de 24/02](../tests/dados_sinteticos/validacao_direcao/10_corrija_me_24-02.xlsx) | **Importações → redações (Corrija-me)**, com **Terça-feira do tema = 24/02/2026** | 2 entregas novas, 3 registros de não entrega e 1 reenvio ignorado. O tema **Consumo consciente e redução de resíduos** é criado. |
| [11 · Lista de auxílios](../tests/dados_sinteticos/validacao_direcao/11_auxilios.csv) | **Auxílios → Gerar relatório**, na seção 8 | 3 matrículas distintas e válidas, 2 encontradas, 1 sem cadastro e 2 linhas recusadas. |
| [12 · Revisão do cadastro](../tests/dados_sinteticos/validacao_direcao/12_cadastro_revisao.csv) | **Importações → cadastro**, com **Data de mudança de turma = 16/02/2026**, na seção 9 | 1 mudança de turma e 1 divergência de nome. |

### Formatos usados no dia a dia

| Fonte | O que preparar antes do envio |
| --- | --- |
| Cadastro | Uma linha por aluno com **matrícula**, **nome**, **turma** e, se houver, **data de ingresso**. No primeiro cadastro, ingresso em branco assume 1º de janeiro do ano informado. Em registros existentes, divergências de nome ou de ingresso são encaminhadas para conferência manual. Uma turma nova pode ser criada durante a importação. |
| Calendário | Uma tabela por tipo, em CSV ou XLSX. Use as datas de início e fim para períodos e ciclos, e uma data por exceção ou tema. Para converter a grade visual do calendário do curso, transcreva as datas para os modelos disponíveis em **Calendário → Importar planilha**. |
| Frequência | A grade **Presença Anual** (ou a aba de grade indicada no formulário), com **Nome**, **Matrícula** e datas nas colunas. Use **P** para presente, **F** para falta, **J** para falta justificada e **S** para sem aula. Use a grade consolidada; as abas diárias de passagens da catraca servem de origem à grade. |
| Simulado | Um relatório do P+ por simulado, em XLSX ou XLSM. Mantenha as abas **Resultados e Classificações TRI** e **Acertos e Porcentagens TRI**, além da coluna **Matrícula** para identificação. Selecione o ciclo pelo intervalo de datas. Uma área com nota e acertos em branco fica sem avaliação. |
| Redações | Uma exportação completa do Corrija-me por tema, com a matrícula em **RM**. Indique a terça de lançamento no formulário. A exportação contém entregas e o FAROL usa o cadastro para registrar quem não entregou. Para ENEM, envie as cinco competências de 0 a 200. Outras bancas usam seus critérios e a nota final informada. Se houver mais de um envio do mesmo aluno, vale o mais recente. |
| Auxílios | Uma única coluna **matrícula**. A lista é usada no momento da geração do relatório. |

O FAROL cruza os registros pela matrícula. Para o CASDvest, a matrícula tem sete dígitos e começa pelos dois últimos dígitos do ano, seguidos de **30** (extensivo) ou **31** (semiextensivo). A base deste roteiro usa matrículas fictícias começando com **S**. Se precisar montar outro arquivo, use **Baixar modelo** na tela da fonte.

### Verificações antes de seguir

- Depois dos arquivos 02 a 05, abra **Calendário** e selecione 2026. Confira o período, os dois ciclos, o tema de 17/02, as duas exceções e **20 dias letivos no ano**. A regra padrão conta os dias úteis dentro dos períodos de aula. As exceções permitem excluir um dia útil ou incluir, por exemplo, um sábado.
- Depois do arquivo 06, abra **Alunos → Ficha** de **Estrela**. O ingresso é 24/02 e a tabela **Frequência por ciclo** deve mostrar **4 dias** no ciclo 2, todos com presença. Na conferência da grade, o registro de 20/02 de Estrela e a marca em 18/02 de Aurora foram avisados e ficaram fora da apuração. O sábado 21/02 contou como dia letivo para quem já havia ingressado.
- Depois do arquivo 08, em **Calendário**, tente **Editar** o ciclo 2, trocando só a data do simulado para 28/02/2026. A tela deve recusar a alteração porque o ciclo tem resultados. Volte ao calendário e confira a data original.
- Para testar uma data inválida em redações, faça uma conferência do arquivo 09 com **18/02/2026**, uma quarta-feira. A tela deve pedir uma terça-feira. Use **17/02/2026** na carga do roteiro.

Se a conferência recusar o arquivo inteiro, verifique o formato, o cabeçalho e o nome da aba antes de tentar de novo. Se houver pendências em todas as linhas, confirme se o cadastro foi importado no ano escolhido e se a coluna de matrícula está preenchida. No P+, confira o intervalo das datas antes de confirmar. A escolha do ciclo é feita no formulário.

## 4. Resolver as pendências

1. Abra **Pendências**. Filtre **Ano letivo = 2026**, **Situação = Pendente** e, primeiro, **Origem = Redação (Corrija-me)**.
2. Antes da associação, confira na ficha de **Brisa** (`S268102`) que o tema de 17/02 aparece como **Não** entregue. Na tela de pendências, marque a linha **Aluno Teste Brisa Exportação**, que está sem matrícula. Digite `S268102` em **Matrícula do aluno** e clique em **Associar selecionadas**.
3. A página informa que o nome do arquivo difere do cadastro. Neste exercício, a linha é de Brisa. Confira a matrícula, marque **Confirmo que as linhas selecionadas são deste aluno** e clique novamente em **Associar selecionadas**. Consulte a situação **Associada** e a ficha de Brisa. A redação de 17/02 deve passar a **Sim**, com nota **750**.
4. Em **Pendências**, limpe o filtro de origem e volte à situação **Pendente**. Marque as duas linhas de `S269999`, uma da frequência e uma do P+. Clique em **Descartar selecionadas**. Elas devem aparecer ao filtrar por **Descartada** e sumir da lista de pendentes.
5. Confira novamente a grade **06**. O resumo deve mostrar **84 registros sem alteração**, **0 alterados** e **0 pendências**. Pode confirmar e conferir a nova entrada na trilha. A linha descartada continua no histórico de pendências.

Em uma importação de trabalho, confira a associação com o cadastro de origem. O nome informado ajuda a revisar a pendência, e a matrícula identifica o aluno a quem os registros serão aplicados.

## 5. Painel, indicadores e ficha

Faça estas conferências antes de mudar limiares, justificar faltas ou alterar turmas. Abra **Painel**. Se houver outro ano em exibição, acrescente `?ano=2026` ao endereço da página inicial do FAROL.

- O painel deve tomar o **ciclo 2** como referência. Os cartões mostram **5 alertas de frequência** e **1 de queda de desempenho**. Clique nos cartões para abrir as listas e conferir os motivos. A lista de frequência tem **Aurora** na semana de 16/02 e **Céu** e **Duna** nas semanas de 16/02 e 23/02. O alerta de queda é de **Brisa**. A contagem da frequência é de alertas semanais, então uma pessoa pode aparecer mais de uma vez.
- Confira **56,8%** de presença no ciclo (25 presenças, incluindo 1 justificada, em 44 registros válidos) e **44,4%** de participação nas redações (4 entregas em 9 registros, depois da associação de Brisa).
- Em **Situação das turmas**, confira os totais **1 queda, 1 estagnado, 2 em evolução e 1 sem avaliação**. Em **Sem presença no ciclo**, confira que a lista tem apenas Duna. Clique nas contagens para ver as listas e use o nome do aluno para abrir a ficha.
- Em **O curso em quatro grupos**, selecione **Ciclo 2** e **Curso todo**, e clique em **Ver**. São quatro alunos nos grupos (25% em cada um) e um fora. Abra um cartão para ver sua lista e abra uma ficha pelo nome. No gráfico **Presença × notas**, o ponto também leva à ficha. Teste o filtro **Turma Farol 1** para ver A e B no recorte, e **Ciclo 1** para ver o estado sem alunos nos grupos. As barras por turma e o gráfico ao longo do ano ajudam a comparar os recortes.
- Em **Indicadores**, filtre **Ciclo 2**. Com **Média das quatro áreas** e todas as turmas, confira **602,5** como média TRI do ciclo 2, contra **600,0** no ciclo 1. Mude a área para **Matemática** e veja **622,5** no ciclo 2. Teste também o filtro por turma e observe a mudança nos gráficos e na tabela. O detalhe do ciclo mostra quantos alunos foram avaliados, presença e participação em redações.

| Aluno | Matrícula | Presença no ciclo 2 | TRI média do ciclo 1 → 2 | Grupo no ciclo 2 |
| --- | --- | --- | --- | --- |
| Aurora | `S268101` | 70% | 600 → 640 (Δ +40) | **A · Em dia** |
| Brisa | `S268102` | 100%, com uma falta justificada | 600 → 540 (Δ −60) | **B · Nota abaixo** |
| Céu | `S268103` | 40% | 600 → 640 (Δ +40) | **C · Presença abaixo** |
| Duna | `S268104` | 0% | 600 → 590 (Δ −10) | **D · Ambas abaixo** |
| Estrela | `S268105` | 100% desde o ingresso | No ciclo 2, 610 em Linguagens e Humanas, com ausência em Natureza e Matemática | Fora dos grupos |

O corte dos grupos é **50% de presença** e **Δ zero**. Duna fica no grupo D por ter presença abaixo de 50% e delta negativo. Seu desempenho aparece como **Estagnado** na situação das turmas, pois a queda de 10 pontos fica dentro do limiar de 30. Os grupos e alertas são indicativos e apoiam o acompanhamento pela Direção.

### O que conferir na ficha individual

- Abra **Alunos → Ficha** de **Brisa**. Confira turma atual, ingresso, evolução de notas (total e por área), delta do próprio histórico, média da turma como referência, frequência por ciclo, alerta com motivo e redações. Em **Presença × notas**, veja o grupo B e a trajetória. Em **Faltas e justificativas**, confira **24/02/2026** como justificada.
- Na ficha de **Aurora**, confira redação de 17/02 com **800** e de 24/02 com **850** (último envio). Na de **Céu**, confira **80** em 24/02, na escala da banca do exemplo. Em **Duna**, confira **Não** em ambos os temas e nota em branco.
- Na ficha de **Estrela**, confira as áreas em que há nota e as áreas marcadas **faltou** no ciclo 2. A média das quatro áreas e o delta ficam sem valor. Compare com Aurora, que tem nota em todas as áreas, mas ainda aparece sem delta no ciclo 1.

## 6. Justificativas e regras de alerta

### Aprovar e retirar uma justificativa

1. Na ficha de **Aurora**, abra **Faltas e justificativas**. Localize **19/02/2026** e clique em **Justificar**. Este ato registra a aprovação. A linha deve indicar **Justificada**.
2. Volte ao painel. A presença do curso sobe para **59,1%** e os alertas ativos de frequência caem de **5 para 4**. Na ficha de Aurora, a presença do ciclo 2 passa de 70% para 80%. O alerta da semana continua no histórico da ficha, marcado como corrigido.
3. Confira e confirme outra vez o arquivo **06** enquanto a falta ainda está justificada. A conferência deve avisar que **1 falta** marcada como **F** na grade continua justificada no FAROL. Abra novamente a tela de faltas para conferir a situação.
4. Clique em **Retirar justificativa** na mesma data para voltar à situação inicial. A linha volta a **Falta** e o painel volta a exibir **5 alertas de frequência**.

### Simular e salvar novos limiares

1. Abra **Regras → Alterar o limiar** na regra de frequência. Digite **4** e clique em **Pré-visualizar**. A prévia compara **3 alunos** no limiar atual com **1 aluno** no novo. A prévia conta pessoas. O painel conta alertas por semana.
2. Clique em **Salvar este limiar**. Confira o recálculo no painel, com **2 alertas semanais de frequência**, ambos de Duna. Em **Regras**, confira o limiar vigente e **Limiares anteriores**. Entre na edição novamente para consultar o histórico com data, autor e valores.
3. Restaure **3** usando os passos de prévia e salvamento.
4. Na regra de desempenho, pré-visualize **70**. A prévia passa de **1 aluno** para **0**. Salve, confira o cartão de queda em **0**, e restaure **30** pelo mesmo fluxo. Abra o quadro de grupos e confira que Brisa continua em B mesmo com a mudança de limiar.
5. Se quiser verificar a validação do formulário, tente pré-visualizar **3,5** na frequência, que exige um número inteiro. Para desempenho, os valores aceitos vão de 1 a 500 pontos. Os alertas apoiam a análise pela Direção. O registro do acompanhamento é feito pela funcionalidade de intervenções.

## 7. Intervenções e desfechos

1. Após restaurar o limiar de desempenho, abra o alerta de **Brisa** pela ficha. Clique no **Registrar intervenção** que aparece junto ao alerta. Confira o campo **Alerta de origem (opcional)** preenchido.
2. Escolha **Contato**, data **02/03/2026**, responsável **Direção de Teste** e descrição **Contato fictício para validar o acompanhamento.** Deixe o desfecho em branco e clique em **Registrar**. Confira a nova intervenção na ficha.
3. Abra **Intervenções** no menu. Filtre pelo nome **Brisa** ou por `S268102`, tipo **Contato**, desfecho **Pendente (sem desfecho)** e datas de **02/03/2026** a **02/03/2026**. O histórico deve mostrar uma linha com data, responsável, alerta de origem e registro pendente.
4. Clique em **registrar** no desfecho, selecione **Em acompanhamento** e salve. Filtre pelo novo desfecho para encontrar a mesma intervenção. A ficha também deve mostrar a atualização. Você pode testar **Atualizar desfecho** mudando para **Resolvido**.
5. Para testar o fluxo sem alerta, entre pela seção **Intervenções** da ficha de **Duna** e clique em **Registrar intervenção**. Registre uma **Conversa** fictícia na mesma data com o campo de alerta em branco. Confira a linha no histórico e o filtro **Tipo**. Faça este teste depois de comparar os números do relatório de auxílios, se quiser reproduzi-los exatamente como na seção 8.

## 8. Relatório de auxílios

1. Abra **Auxílios**, selecione **2026**, anexe o arquivo **11** e clique em **Gerar relatório**.
2. Confira **3 matrículas válidas**, **2 encontradas entre os alunos do ano**, **1 sem aluno correspondente** e **2 linhas recusadas** (matrícula repetida e formato inválido).
3. No **Resumo para a prestação de contas**, confira **2 beneficiados** e **3 demais alunos**. O quadro compara frequência, participação nas redações, desempenho no ciclo, alunos com alerta e intervenções por desfecho. Se você registrou o contato de Brisa, a coluna de beneficiados mostra **1 intervenção** e o desfecho escolhido.
4. Na **Lista nominal**, confira apenas Aurora e Brisa. Use o nome para abrir a ficha. Volte a **Auxílios** pelo menu. Para obter outro relatório, é preciso anexar o arquivo de novo.
5. Abra **Importações** e **Pendências** e confira que o envio de auxílios não gerou entrada em nenhuma delas. O relatório usa a lista durante a consulta e a prestação de contas usa apenas o bloco agregado.

Para uso com dados reais, confirme com a Direção se o consentimento da matrícula cobre o uso da lista de auxílios. [Regras de uso dos dados de auxílios](dominio-casd.md#alunos-beneficiados-por-auxílios-rf021-sm-80)

## 9. Cadastro e calendário pela interface

Faça estes testes depois de conferir os números do painel e de auxílios.

### Revisar alunos e turmas

1. Abra **Turmas** e entre em **Turma Farol 2 (2026)**. Antes da revisão, devem aparecer **Céu**, **Duna** e **Estrela**. Em **Alunos**, teste os filtros **Ano letivo**, **Turma** e **Situação**.
2. Importe o arquivo **12** conforme a tabela. Duna deve aparecer na **Turma Farol 1**. Na ficha de Duna, em **Turmas**, confira a turma anterior e a atual. Em **Indicadores**, com **Média das quatro áreas**, a Turma Farol 1 tem **2 avaliados no ciclo 1** e **3 no ciclo 2**, quando passa a incluir Duna. Em **Editar** na lista de alunos, confira a alteração de turma e seu autor no histórico.
3. A divergência de nome de Aurora exige revisão manual. Confira que o nome original continua no cadastro. Em **Alunos → Editar**, altere-o para **Aluno Teste Aurora Revisão**, salve e abra novamente a edição para conferir valor anterior, valor novo, data e autor.
4. Abra **Turmas → Nova turma** e crie **Turma Farol 3**, ano **2026**. Edite seu nome para **Turma Farol 3 Revisada** e confira a trilha da alteração na edição. Teste a rejeição de um nome duplicado no mesmo ano.
5. Em **Alunos → Novo aluno**, crie **Aluno Teste Lago** com matrícula `S268106`, ingresso em **02/03/2026** e **Turma Farol 3 Revisada**. A lista deve mostrar o aluno como **Ativo**. Edite o aluno, selecione **Turma Farol 1** e tente salvar com a **Data da mudança de turma** vazia. Depois preencha **03/03/2026**, salve e confira o histórico na ficha.
6. Edite Lago para **Desligado**. Primeiro tente salvar com **Data de saída** vazia e confira a validação. Preencha **06/03/2026** e salve. Use o filtro **Desligado** para encontrá-lo. Na ficha, confira a situação e a data. A opção **Inválido (lançado por engano)** mantém o cadastro no histórico e o retira da listagem padrão. Use **Todas, inclusive inválidos** para conferir esse caso em Lago, se quiser validar as duas situações.

### Criar e editar itens do calendário

1. Abra **Calendário**, selecione 2026 e altere apenas a descrição do período de fevereiro. Reabra **Editar** para conferir o histórico. Teste a mesma atualização via planilha, se desejar, salvando uma cópia de **02** com as mesmas datas e uma nova descrição. A conferência deve contar **1 atualizado**. Também pode criar outro período pela importação de **Períodos letivos**.
2. Em **Novo → dia**, registre uma exceção em **04/03/2026** com a opção **Dia letivo** desmarcada e uma descrição fictícia. Confira o item em **Dias não letivos** e teste a edição da descrição.
3. Em **Novo → ciclo**, cadastre um ciclo de **02/03/2026** a **15/03/2026**, com simulado em **15/03/2026**. Confira as datas em **Ciclos e temas de redação**. Um ciclo sem resultados ainda permite editar as datas. Tente cadastrar um ciclo que se sobreponha ao de fevereiro para conferir a validação.
4. Em **Novo → tema**, cadastre um tema fictício em **03/03/2026**, uma terça-feira. Confira sua presença em **Temas por semana** e no ciclo de março. Abra **Editar** para ajustar o título e conferir o histórico. Se tentar cadastrar em outro dia da semana, a tela deve recusar.

## 10. Gestão de usuários e perfis

1. Abra **Usuários → Novo usuário**. Crie `membro.teste`, com e-mail fictício `membro.teste@example.test`, perfil **Membro de diretoria**, e salve. Na edição, clique em **Gerar link para definir senha** e copie o link antes de sair da tela. O link é exibido uma vez.
2. Abra-o numa janela privativa, escolha uma senha para a conta fictícia e clique em **Salvar senha**. Volte ao endereço do FAROL e entre com a conta. Teste o link novamente para conferir que já foi usado.
3. Pelo cabeçalho da sessão de Membro, abra **Painel**, **Indicadores**, **Regras**, **Alunos**, **Turmas** e **Calendário**. O painel e os indicadores mostram agregados. No quadro de grupos, os pontos e contagens ficam sem nomes ou links para fichas. Nas listas de cadastro de **Alunos** e **Turmas** aparecem nomes e matrículas, com ações de edição reservadas à Direção. Esse acesso às listas está registrado na SM #58 para validação da Direção.
4. Copie, na sessão Diretora, o endereço da ficha de Aurora ou de uma lista nominal de alertas ou grupos. Abra-o na sessão de Membro e confira **acesso negado (403)**. Repita para **Importações**, **Pendências**, **Auxílios**, **Intervenções**, **Usuários** e a edição de uma regra. Use a barra de endereços para fazer o teste.
5. Na sessão Diretora, edite a conta de teste para o perfil **Diretor** e salve. Reabra o painel na outra sessão e confira o novo perfil e o acesso à ficha. Depois volte o perfil a **Membro de diretoria** e desmarque **Acesso ativo**. A conta deve perder o acesso, inclusive na sessão já aberta. Consulte o **Histórico de alterações** na edição.
6. Para testar redefinição, reative a conta, gere um segundo link e confira que a senha anterior perdeu a validade. Abra o novo link, defina outra senha e entre novamente. A conta deve estar **ativa** e com e-mail para o teste de fechamento do ciclo.

**Teste adicional de login.** Use uma conta fictícia descartável e tente entrar com senha errada até aparecer o aviso de bloqueio temporário. A configuração inicial é de 5 tentativas e 15 minutos. Confira que a senha correta continua bloqueada durante o prazo. Após o prazo e com a senha correta, a conta deve voltar a entrar. Para verificar o login único, abra `/admin/login/` sem sessão. A aplicação deve levar à mesma tela **Entrar**. O admin técnico exige conta habilitada para ele. A gestão cotidiana das contas usa **Usuários**.

## 11. E-mail de fechamento de ciclo

Mantenha ativa a conta de Membro criada na seção 10. O FAROL envia o resumo para contas comuns ativas com e-mail, incluindo Diretor e Membro. A conta criada pelo comando `createsuperuser` fica fora da lista de destinatários. A data de referência abaixo é o dia seguinte ao fechamento do ciclo 2.

**Com Docker**, use o terminal na pasta do projeto e mantenha os serviços em execução. Após rodar os comandos, abra a [caixa de teste do Mailpit](http://localhost:8025/) para ler a mensagem.

```bash
docker compose exec app python manage.py gerar_alertas --ano 2026
docker compose exec app python manage.py notificar_ciclo --data 2026-03-02
docker compose exec app python manage.py notificar_ciclo --data 2026-03-02
```

**Sem Docker**, abra um segundo terminal na pasta do projeto, mantendo o FAROL no primeiro. Com `EMAIL_URL=consolemail://`, a mensagem aparece no terminal em que você roda o comando.

```bash
uv run --locked --no-dev python manage.py gerar_alertas --ano 2026
uv run --locked --no-dev python manage.py notificar_ciclo --data 2026-03-02
uv run --locked --no-dev python manage.py notificar_ciclo --data 2026-03-02
```

A mensagem do ciclo 2 deve mostrar **16/02 a 01/03**, totais do curso e por turma, frequência, participação nas redações, situação de desempenho e contagens de alertas. Confira que o conteúdo traz apenas os agregados e que o link abre o painel local. A segunda execução de `notificar_ciclo` deve informar que não há ciclo a notificar e gerar zero mensagens novas.

## 12. Registro da validação

Marque o item após conferir o resultado. Para uma divergência, registre a etapa, o perfil, o ano, o arquivo, os parâmetros, o resultado apresentado e o esperado. Anexe, se necessário, uma captura da sessão com dados fictícios.

- [ ] Baixei o código e as planilhas, iniciei o FAROL no meu computador e criei a primeira conta Diretora.
- [ ] Entrei, saí e conferi as permissões de Diretor e de Membro, inclusive por endereço direto.
- [ ] Criei uma conta de teste, defini e redefini senha, alterei perfil e revoguei o acesso.
- [ ] Conferi e confirmei o cadastro, o calendário, a frequência, os dois simulados e os dois temas de redação.
- [ ] Conferi os avisos, a linha recusada, a trilha de importações e a reimportação sem duplicação.
- [ ] Associei a redação sem RM e descartei as linhas sem cadastro, conferindo o resultado em **Pendências**.
- [ ] Conferi painel, alertas, grupos, filtros, ficha e indicadores por turma, área e ciclo.
- [ ] Justifiquei e retirei uma falta. Testei a preservação da justificativa na reimportação.
- [ ] Pré-visualizei, salvei e restaurei os limiares de frequência e de desempenho.
- [ ] Registrei intervenções, atualizei um desfecho e filtrei o histórico.
- [ ] Gerei o relatório de auxílios e conferi as contagens, a lista nominal e a ausência de registros do envio.
- [ ] Revisei alunos, turmas e calendário, conferindo os históricos de alterações disponíveis.
- [ ] Conferi o e-mail de fechamento no ambiente local e a ausência de reenvio para o mesmo ciclo.
