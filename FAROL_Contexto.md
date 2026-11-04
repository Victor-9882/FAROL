# FAROL — Contexto completo do projeto

> **F**erramenta de **A**companhamento, **R**etenção e **O**rientação **L**ongitudinal
> Projeto da disciplina **CSI-28 — Fundamentos de Engenharia de Software** (ITA / IEC, 2026.2)
> Professores: Karla Donato Fook e Maylon Pires Macedo
> Documento de contexto consolidado em 04/11/2026 a partir dos Labs 01–05 e da ata da 1ª reunião com o cliente.

---

## 1. Resumo em uma página

- **O que é:** aplicação web de apoio à decisão para a **Direção do CASD** (Curso Alberto Santos Dumont), cursinho popular gratuito de São José dos Campos gerido por alunos do ITA.
- **Problema:** o acompanhamento dos alunos está espalhado em planilhas independentes (frequência, simulados, redações), cada uma com um responsável e consultada isoladamente. Sinais de risco só são percebidos em conjunto quando o aluno já evadiu. Hoje o intervalo entre sinal e ação é de **semanas**.
- **Objetivo:** reduzir esse intervalo para **poucos dias**, consolidando os dados em uma base única e gerando **alertas precoces** (desengajamento, queda de desempenho) e destaques (alunos em evolução).
- **Princípio central:** **regras interpretáveis**, não modelos preditivos opacos. Todo alerta diz o tipo e o motivo. Alertas são **estritamente indicativos**: nunca servem para punição, classificação pública ou exclusão.
- **Escopo da v1:** apenas **CASDvest** (~500 alunos). CASDinho fora do escopo.
- **Usuários:** só a gestão do CASD (Diretor com acesso total; Membro de diretoria só com dados agregados). Uso **pelo celular**, semanal (frequência) e a cada ciclo de 2 semanas (desempenho).
- **Processo:** Kanban. **Arquitetura:** camadas em torno de um banco relacional.
- **Estado atual (nov/2026):** modelagem, configuração e plano de testes entregues; **ainda sem código**. Repositório público criado em `github.com/Victor-9882/FAROL` com os arquivos iniciais; stack ainda não definida.

---

## 2. Equipe e papéis

| Integrante | Papel | Dedicação (h/sem) | Responsabilidades principais |
|---|---|---|---|
| **Victor Alves** | Gerente de projeto **e** gerente de configuração | 2–4 | Cronograma, Kanban, reuniões, interface com a Direção do CASD, riscos, entregas; mantém o Registro de Configuração, aprova SMs, estabelece linhas de base e tags, administra acessos, libera versões para produção |
| **Eduardo Henrique Camargo de Toledo** | Analista de sistemas | 2–3 | Elicitação e especificação de requisitos, modelagem (classes, DER, casos de uso), rastreabilidade, análise de impacto das SMs |
| **Matheus Felipe Ramos Borges** | Programador | 1–3 | Aplicação web (apresentação, negócio, persistência), modelagem física do banco; revisa PRs do Pietro |
| **Pietro Maragno Trindade Marcucci** | Programador | 1–3 | Aplicação web, importação e tratamento de dados, dependências e contêineres; revisa PRs do Matheus |
| **Yuri Barros Mendes** | Engenheiro de testes | 1–3 | Planejamento e execução de testes, bases sintéticas (NF017), CI, auditorias de configuração, apoio à validação com o cliente |
| **Direção do CASD** | Cliente | — | Aprova mudanças de requisito e de escopo |

Total estimado: 7–16 h/semana.

> ⚠️ **Inconsistência a corrigir:** no Plano de Testes (Lab 05), o nível *Sistema* aparece como responsabilidade de "Victor (engenheiro de testes)", mas em todos os outros documentos o engenheiro de testes é o **Yuri**.

---

## 3. O cliente: CASD

- ONG com mais de duas décadas, educação gratuita para jovens em vulnerabilidade socioeconômica.
- Duas frentes: **CASDinho** (vestibulinhos) e **CASDvest** (vestibulares). Atividades à noite durante a semana e o dia todo nos fins de semana.
- **Gestão** (presidência, coordenações, diretorias) feita por alunos do ITA, voluntários, com **rotatividade anual**.
- Funcionários assalariados: financeiro, jurídico, motorista, atendentes da sede.
- ~50 professores voluntários, produtores de material didático e plantonistas.

**Consequências para o sistema:**
1. **Rotatividade anual da gestão** → o sistema precisa reter o histórico e ser operável por um gestor recém-empossado sem treinamento extenso.
2. **Tempo escasso dos gestores** → entregar conclusões, não dados brutos; informação em poucos cliques.
3. **Quem alimenta os dados é heterogêneo** → ingestão tolerante a falhas e explícita sobre inconsistências.

---

## 4. Levantamento com o cliente — 1ª reunião (03/09/2026, 20:20–21:15)

Participantes: Victor, Pietro, Matheus, Yuri, Eduardo, Marcela.

### B1 — Problema e objetivo
- Se fizesse só uma coisa bem: **alertas** e **visão geral do aluno**.
- Decisão tomada "no escuro" hoje: **quem são os alunos que precisam de ajuda**. Atualmente só se olha o topo do simulado e pergunta-se como estão.
- Cobertura: **~500 alunos**.
- Ferramentas atuais com as quais convive: **P+** e **planilhas**.

### B2 — Usuários e perfis
- Quem abre: **diretores e membros do Desenvolvimento**.
- Dispositivo: **celular** (não ficará no PC da sede). Frequência: a cada 2 semanas (ciclo do simulado).
- Familiaridade tecnológica: alta (iteanos).
- Visibilidade: **Diretor vê tudo; Membro restrito**. Cadastro/alteração: **Diretor**; Membro só consulta.
- Ninguém de fora da gestão (professor, plantonista, aluno, responsáveis) precisa de acesso.
- Passagem de gestão: considerado irrelevante pelo cliente.

### B3 — Fontes de dados
| Dado | Origem | Responsável / periodicidade |
|---|---|---|
| Presença em aulas | Catraca (download já existe via Google Script) → planilha "Controle de Presença 2026" | RH, semanal |
| Presença em simulados | P+ → planilha | — |
| Notas de simulado | Exportadas do P+ e coladas em planilha (ex.: "Notas Alunos FUVEST 1 – PEI") | DES, sem periodicidade fixa |
| Presença/entregas de redação | Exportadas do Corrija-me | — |
| Dashboard de redação (notas, nº de entregas) | Corrija-me | — |
| Cadastro dos alunos | Planilha "Banco de Dados – CASDvest 2026" (dados da matrícula) | — |
| Calendário de simulados e período letivo | Planilha baseada no Poliedro | — |

- Cópias reais/amostras e dados de anos anteriores: **podem ser fornecidos**.
- Identificação do aluno: **nº de matrícula e nome**.
- Problemas de preenchimento relatados: nenhum (mas a revisão posterior encontrou matrículas em branco no Corrija-me).
- Dados **não coletados hoje** e desejados: **horário da catraca** e **presença por aula específica**.
- Entrada no sistema: P+ e Corrija-me "vai ter que dar o gás para automatizar".

> Os links das planilhas reais estão na ata (`1ª Reunião 03_09.docx`, no Project) e **não devem ser copiados** para o repositório, que é público.

### B4 — Regras de negócio
- **Falta:** sem registro na catraca. Não há tolerância de atraso. Justificativas automatizadas; **justificada conta como presença**.
- **Aluno em risco:** já existe uma regra implementada na planilha de banco de dados (perguntar ao **Olaf**).
- **Evasão:** sem definição formal (perguntar ao Olaf).
- **Queda de desempenho:** sem resposta definida.
- **Estagnado / em evolução:** basta o **delta de nota**, com um "graficozinho".
- **Notas:** **TRI (padrão ENEM)** e também **acertos brutos**.
- **Calendário:** calendário de simulados e período letivo baseado no Poliedro. **Toda terça há um tema novo de redação.**
- **Turmas:** divisão aleatória; **várias chamadas de matrícula ao longo do ano**.
- **Desligamento:** **não existe**.

### B5 — Alertas e relatórios
- Canal: **tela ao abrir o sistema** + **e-mail de fim de ciclo**.
- Frequência: **RH (presença) semanal; DES (desempenho) a cada ciclo (2 semanas)**.
- Fluxo real: entrar no site → ver relatório de alunos inativos, queda de desempenho, análise geral dos simulados → **puxar reunião com membros**.
- **Registrar intervenção:** deve; armazenar o que foi feito para cada aluno.
- Volume: **1 tipo de alerta por semana**.
- Explicação do alerta: sim, basta o tipo (ex.: "queda de desempenho").
- Visões agregadas: **por turma, evolução no tempo, por área de conhecimento**.
- Prestação de contas: **sim**, acompanhamento da evolução de alunos beneficiados por auxílios (vale-transporte, empréstimo de computadores, cestas básicas).

### Pendências da reunião
- B6 não preenchido; TO DO: atualizar o quadro de post-its.

---

## 5. Requisitos (Documento de Requisitos v1.0 — Lab 02, 10/09/2026)

Convenção: **RF** (funcionais/casos de uso), **RN** (regras de negócio), **NF** (não funcionais), numeração contínua. Prioridades: **Essencial / Importante / Desejável**. Modelo: UFU/FACOM.

**Técnicas de elicitação:** entrevista estruturada (principal), análise de documentos (planilhas), histórias de usuário, prototipação, brainstorming interno.

### 5.1 Abrangência
**Fará:** importar frequência, simulados, redações, cadastro e calendário; ficha longitudinal por aluno; alertas de frequência (semanais) e desempenho (por ciclo); visões agregadas por turma, área e tempo; registro de intervenções e desfechos; relatórios de prestação de contas.

**Não fará:** atender o CASDinho; substituir P+, Corrija-me ou catraca (só consome seus dados); tomar decisões sobre alunos; predição estatística de evasão; dar acesso a professores, plantonistas, alunos ou responsáveis; tratar dados socioeconômicos ou de saúde.

### 5.2 Sistemas relacionados
| Sistema | Interação |
|---|---|
| Catraca da sede | Importação do arquivo exportado por script existente |
| P+ | Importação de notas e presença em simulados; integração automática desejável |
| Corrija-me | Importação de entregas e notas de redação; integração automática desejável |
| Google Sheets | Importação (CSV/XLSX) do cadastro e do calendário |
| Serviço de e-mail | Notificação de fechamento de ciclo |

### 5.3 Perfis
| Perfil | Permissões |
|---|---|
| **Diretor** | Tudo: dados nominais, importar/alterar, parametrizar regras, registrar intervenções, relatórios, gerenciar acessos |
| **Membro de diretoria** | Só consulta de indicadores agregados e não nominais |

### 5.4 Requisitos funcionais
| ID | Caso de uso | Prioridade |
|---|---|---|
| **Acesso** | | |
| RF001 | Autenticar usuário (perfil define o que é exibido) | Essencial |
| RF002 | Gerenciar usuários e perfis (continuidade na troca de gestão) | Importante |
| **Dados** (ator: Diretor; identificação por [RN003]) | | |
| RF003 | Importar frequência da catraca, aplicando RN001 e RN005 | Essencial |
| RF004 | Importar simulados (P+): TRI e acertos brutos, por prova e área | Essencial |
| RF005 | Importar redação (Corrija-me): entregas e notas por competência, por tema semanal | Essencial |
| RF006 | Manter cadastro de alunos e turmas (matrícula, nome, turma, ingresso), com histórico | Essencial |
| RF007 | Manter calendário letivo, simulados, ciclos e temas de redação | Essencial |
| RF008 | Registrar justificativa de falta (RN002) | Importante |
| RF009 | Integração automática com P+ e Corrija-me | Desejável |
| **Acompanhamento** | | |
| RF010 | Painel inicial com alertas ativos e situação das turmas no ciclo | Essencial |
| RF011 | Ficha longitudinal do aluno (evolução de notas, frequência, redações, alertas, intervenções) | Essencial |
| RF012 | Indicadores agregados por turma, área e evolução no tempo | Essencial |
| RF013 | Comparar aluno com seu histórico e com a média da turma (delta) | Importante |
| **Alertas** | | |
| RF014 | Alerta semanal de frequência (faltas não justificadas acima do limiar) | Essencial |
| RF015 | Alerta de desempenho no fim de cada ciclo, classificando conforme RN008 | Essencial |
| RF016 | Destacar alunos em evolução consistente | Importante |
| RF017 | E-mail de fechamento de ciclo, agregado e sem nomes | Importante |
| RF018 | Parametrizar limiares sem alterar código, com pré-visualização de quantos alunos seriam sinalizados | Importante |
| **Intervenções** | | |
| RF019 | Registrar intervenção (contato, conversa, encaminhamento) com responsável, data e desfecho | Essencial |
| RF020 | Consultar histórico de intervenções por aluno, tipo, desfecho ou período | Importante |
| **Relatórios** | | |
| RF021 | Relatório de alunos beneficiados por auxílios (prestação de contas) | Importante |
| RF022 | Exportar listas e indicadores em CSV/PDF respeitando o perfil | Desejável |

### 5.5 Fluxos dos 4 casos de uso centrais
- **RF003 Importar frequência:** diretor envia arquivo + período → sistema valida formato e associa por matrícula → aplica RN001/RN005 → mostra resumo (importados, ignorados, inconsistentes) → diretor confirma. *Secundários:* matrícula não encontrada → isolada para associação manual; período já importado → exige confirmação para substituir.
- **RF010 Painel inicial:** autentica → calcula alertas → exibe inativos, queda, evolução e situação por turma → usuário seleciona alerta e vê a lista. *Secundários:* perfil Membro → só contagens agregadas; sem dados → mostra data da última importação.
- **RF015 Alerta de desempenho** (ator: sistema temporizado): no fim do ciclo calcula delta total e por área → classifica em queda/estagnado/evolução (RN008) → registra alerta com tipo e área → exibe no painel. *Pré-condição:* ≥ 2 simulados. *Secundários:* ausente no simulado → RN009; primeiro simulado → sem base de comparação.
- **RF019 Registrar intervenção:** diretor informa tipo, data, responsável, descrição → sistema vincula ao alerta → desfecho (resolvido, em acompanhamento, sem retorno), podendo ser registrado depois. *Secundário:* intervenção sem alerta associado.

### 5.6 Regras de negócio
| ID | Regra |
|---|---|
| RN001 | Falta = ausência de registro na catraca em dia letivo; sem tolerância de atraso |
| RN002 | Ausência justificada e aprovada pela Direção conta como presença |
| RN003 | Aluno identificado unicamente pela matrícula; nome é verificação secundária |
| RN004 | Aluno entra nos indicadores a partir da data de ingresso (várias chamadas no ano) |
| RN005 | Feriados e recessos não são dias letivos |
| RN006 | Ciclo de desempenho = 2 semanas entre simulados, definido pelo calendário |
| RN007 | Novo tema de redação toda terça-feira |
| RN008 | Queda/estagnado/evolução pelo delta em relação ao **próprio histórico**, não à média da turma |
| RN009 | Ausente no simulado não é avaliado em desempenho naquele ciclo; ausência vira indicador de frequência |
| RN010 | Notas em TRI (padrão ENEM) e acertos brutos, por prova e área |
| RN011 | Turmas por divisão aleatória; mudança de turma preserva histórico |
| RN012 | Não há desligamento; alertas estritamente indicativos, sem punição, classificação pública ou exclusão |
| RN013 | Só a Direção acessa dados nominais; demais membros veem só agregados |
| RN014 | Dados de menores apoiados no consentimento dos responsáveis (termo na matrícula, LGPD art. 14) |

### 5.7 Requisitos não funcionais
| ID | Requisito | Prioridade |
|---|---|---|
| **Usabilidade** | | |
| NF001 | Uso pleno em navegador de celular (Android e iOS), responsivo | Essencial |
| NF002 | Alertas e indicadores em ≤ 3 interações a partir da tela inicial | Essencial |
| NF003 | Operável por diretor recém-empossado com guia de até 2 páginas | Importante |
| NF004 | Todo alerta exibe tipo e motivo | Essencial |
| NF005 | No máximo 1 tipo de alerta por semana | Importante |
| **Confiabilidade** | | |
| NF006 | Importação tolerante a falhas: inconsistentes isolados e listados | Essencial |
| NF007 | Histórico preservado entre anos letivos e gestões | Essencial |
| NF008 | Importações repetidas sem duplicidade; sobreposição exige confirmação | Importante |
| NF009 | Alteração manual registra autor, data e valor anterior | Importante |
| **Desempenho** | | |
| NF010 | Painel e consultas em ≤ 5 s com base completa | Importante |
| NF011 | Importação de 500 alunos em ≤ 2 min | Importante |
| NF012 | 500 alunos ativos, 20 usuários, 3 anos de histórico | Importante |
| **Segurança** | | |
| NF013 | Dados nominais só para Diretor (RN013) | Essencial |
| NF014 | Autenticação obrigatória para qualquer dado de aluno | Essencial |
| NF015 | Minimização: só identificação, turma, frequência, notas e participação | Essencial |
| NF016 | Log de acesso a fichas individuais | Desejável |
| NF017 | Dev e teste só com bases anonimizadas ou sintéticas | Essencial |
| **Distribuição** | | |
| NF018 | Web, sem instalação | Essencial |
| NF019 | Gestão de acessos pelo próprio sistema | Importante |
| **Padrões** | | |
| NF020 | Conformidade com a LGPD (art. 14, RN014) | Essencial |
| NF021 | Regras documentadas e interpretáveis; sem modelos opacos nesta versão | Essencial |
| NF022 | Alertas indicativos (RN012) | Essencial |
| **Hardware e software** | | |
| NF023 | Navegadores modernos desktop e móveis | Essencial |
| NF024 | Hospedagem de baixo custo, banco relacional, backup periódico | Importante |
| NF025 | Importação CSV e XLSX | Essencial |

### 5.8 Questões em aberto (não bloqueiam: limiares são configuráveis via RF018)
1. **Definição de evasão:** não há critério formal.
2. **Regra de risco existente** na planilha de banco de dados (Olaf): levantar e comparar.
3. **Limiar de queda de desempenho:** sem acordo.
4. **Dados não coletados:** horário da catraca e presença por aula.
5. **Automação P+ / Corrija-me:** viabilidade técnica não avaliada.

---

## 6. LGPD e ética (Lab 01 + RN/NF)
- Minimização: sem dados socioeconômicos ou de saúde.
- Dev/teste só com dados anonimizados ou sintéticos.
- Controle de acesso por perfil.
- Alertas indicativos, nunca punitivos.
- Base legal citada: **art. 4º, I** (maiores de idade; uso não econômico) e **art. 14** (menores: consentimento de pelo menos um responsável, já coletado por termo na matrícula).
- **Nenhum dado real de aluno pode ser enviado a LLMs** (Plano de Testes).

---

## 7. Modelo de processo — Kanban (Lab 03)

| Modelo | Adequação |
|---|---|
| Cascata | Inadequado: requisitos dependem de validação contínua com cliente voluntário |
| Incremental | Parcial: exige planejamento antecipado de incrementos, conflita com rotatividade |
| Evolutivo (prototipagem) | Não define como o fluxo diário é gerenciado |
| **Kanban** | **Adequado** |

**Justificativa:** carga irregular da equipe (sem iterações fixas), alinhamento aos laboratórios da disciplina como marcos naturais, gestão visual para equipe e cliente.

**Operacionalização:** quadro dividido pelos módulos (Ingestão, Indicadores, Alertas, Intervenções/Relatórios), colunas A Fazer → Em Desenvolvimento → Em Revisão → Concluído, limites de WIP por integrante. Será criado no **GitHub Projects** junto com o repositório (cada cartão = issue).

---

## 8. Arquitetura (Lab 03)

Arquitetura em camadas em torno de um **banco relacional central**:

1. **Integração e Ingestão:** fontes externas (catraca, P+, Corrija-me, Google Sheets) → Agendador → **Workers de ETL** que validam, normalizam e isolam inconsistências (NF006).
2. **Inteligência:** Agendador → **Motor de Indicadores** (frequência, desempenho, participação) → **Motor de Regras** (parametrizável, interpretável, NF021) → grava sinalizações.
3. **Aplicação Core:** módulos **Gestão de Alunos**, **Alertas**, **Intervenções**.
4. **Relatórios e Notificações:** Serviço de Relatórios e Serviço de Notificações (e-mail de fim de ciclo).
5. **Apresentação:** web responsiva, sem instalação, otimizada para celular.

### Modelo de domínio (diagrama de classes / DER)
- **Aluno** pertence a uma **Turma** e acumula **RegistroFrequencia**, **ResultadoSimulado**, **ResultadoRedacao** (histórico preservado em mudança de turma, RN011).
- **Alerta** origina-se de indicadores segundo **RegraAlerta** (RF018) e pode gerar uma ou mais **Intervencao**, registradas por um **Usuario** Diretor (RF019).
- Matrícula como identificador único em todas as tabelas (RN003); nada é excluído entre anos/gestões (NF007).
- ⚠️ A revisão estática apontou que **falta histórico de turmas no DER** (exigido por RN011) — corrigir.

### Protótipo de interface
- Herdado do **PEI** (projeto anterior, feito para outra organização, com nomenclatura própria como escores SE e SD).
- **Tela principal:** lista de alunos da turma + gráfico de dispersão frequência × desempenho em quadrantes (baixa/baixa = crítico), filtro por ciclo (geral ou ciclo específico), alternância gráfico/tabela.
- **Ficha do aluno:** evolução entre ciclos (linhas de frequência e desempenho), zoom por área, alertas emitidos, bloco de ações sugeridas (no FAROL vira registro formal de intervenção com responsável, data e desfecho).

---

## 9. Cronograma (Lab 03)

| Fase | Atividades | Duração | Status (na entrega do Lab 03) |
|---|---|---|---|
| Levantamento de Requisitos | Entrevista, planilhas, Labs 01–02 | 4 sem | Concluída |
| Relatório Descritivo e Modelagem | Arquitetura, classes, DER, processo (Lab 03) | 1 sem | Em andamento |
| Prototipagem | Telas baixa/média fidelidade, validação com Direção | 2 sem | Planejada |
| Dev — Ingestão | Importação de planilhas, inconsistências | 2 sem | Planejada |
| Dev — Indicadores e Alertas | Indicadores, motor de regras | 2 sem | Planejada |
| Dev — Intervenções e Relatórios | Intervenções, relatórios, e-mail | 1,5 sem | Planejada |
| Testes e Validação | Dados reais/anonimizados, validação com usuário externo | 1,5 sem | Planejada |
| Entrega Final | Consolidação, documentação, apresentação | 1 sem | Planejada |

Total ≈ 10 semanas após o relatório descritivo. Entrega final da disciplina: 1ª semana de exames.

---

## 10. Controle de configuração (Lab 04 — `FAROL_GConfig.pdf`, v1.0, 15/10/2026)

Definição ampla de configuração: código, requisitos, documentação, executáveis, bibliotecas, processos, ferramentas, infraestrutura. Práticas marcadas como **Em uso / Adotado / Planejado**.

### Itens de configuração
| ID | Item | Local | Resp. | Situação |
|---|---|---|---|---|
| IC-01 | Proposta, Requisitos, Relatório Descritivo | .tex + PDF / Drive | Victor, Eduardo | Em uso |
| IC-02 | Fontes dos diagramas | .drawio, .pptx / Drive | Eduardo | Em uso |
| IC-03 | Atas com o cliente | Google Docs / Drive | Victor | Em uso |
| IC-04 | Planilhas reais do CASD | XLSX / Drive (restrito) | Victor | Em uso |
| IC-05 | Registro de Configuração e Mudanças | Google Sheets / Drive | Victor | Adotado |
| IC-06 | Plano de configuração | .tex + PDF / Drive | Victor | Adotado |
| IC-07 | Código, esquema do banco, migrações | Git | Matheus, Pietro | Planejado |
| IC-08 | Dependências, contêineres, `.env.example` | Git | Pietro | Planejado |
| IC-09 | Pipeline de CI, testes, bases sintéticas | Git | Yuri | Planejado |
| IC-10 | Valores padrão das regras de alerta + guia de uso | Git | Eduardo | Planejado |
| IC-11 | Hospedagem, banco de produção, backup | Provedor de baixo custo | Victor | Planejado |

### Linhas de base
LB-0 a LB-2 (Labs 01–03, estabelecidas) · LB-3 (Lab 04) · **v0.1.0** protótipo validado · **v0.2.0–v0.4.0** Ingestão; Indicadores e Alertas; Intervenções e Relatórios · **v1.0.0** entrega final validada.

### Ferramentas
Google Drive, Docs e Sheets (em uso) · LaTeX, Draw.io, PowerPoint (em uso) · Git + GitHub, GitHub Issues/Projects, GitHub Actions, Docker Compose (planejados). Critérios: custo zero, sem servidor próprio, continuidade entre gestões.

### Convenções
- Documentos: `FAROL_<Artefato>_v<maior>.<menor>.pdf` (maior = mudança de escopo aprovada; menor = correções), com histórico de revisões. Nomes exigidos pela disciplina prevalecem.
- Diagramas: fonte ao lado da imagem exportada, mesmo nome base.
- Software: **SemVer** por tags.

### Estrutura do Drive
```
FAROL/
  00_Gestao/           atas e Registro de Configuração
  01_Entregas/         PDFs submetidos – somente leitura
  02_Fontes/           .tex
  03_Diagramas/        .drawio, .pptx, imagens
  04_Dados_Cliente/    planilhas reais – acesso restrito
  05_Referencias/      enunciados e bibliografia
```

### Controle de mudanças (Solicitação de Mudança — SM)
Registrar → analisar impacto (RF/RN/NF) → altera requisito? (sim: validar com a Direção) → aprovar (gerente de config.) → implementar (branch ou cópia) → revisar (outro integrante) → integrar, versionar e registrar.
Quem implementa não revisa. SMs rejeitadas ficam registradas. Mudança de requisito → nova versão maior do Doc. de Requisitos; mudança de arquitetura/dados → atualizar Relatório Descritivo e diagramas.

### Versionamento e CI (planejado)
- **Monorepo:** `ingestao/`, `inteligencia/`, `core/`, `relatorios/`, `web/`, `db/migrations/`, `tests/`, `docs/`.
- `.gitignore` exclui `.env` e planilhas fora de `tests/dados_sinteticos/`.
- **Trunk-Based Development:** `main` protegida, PR aprovado por outro integrante + CI verde; branches curtas (ex.: `feat/RF003-importar-frequencia`), integradas em ≤ 1 semana.
- **Conventional Commits** citando o requisito → rastreabilidade requisito → issue → commit → PR → tag.
- **CI (GitHub Actions):** ambiente, estilo, migrações em banco vazio, testes (prioridade RN001, RN002, RN005, RN008, RN009) com dados sintéticos.
- **Ambientes:** dev e homologação com dados sintéticos; produção com dados reais, só versões com tag, liberadas manualmente pelo gerente de configuração. Credenciais em `.env` e GitHub Secrets; banco só por migrações; backup periódico.
- **Auditoria** a cada linha de base, conduzida pelo engenheiro de testes, anotada no IC-05.

> ⚠️ **Divergência com o planejado:** o Lab 04 previa o repositório numa **organização do GitHub** (para transferir ao CASD no fim). Na prática ele foi criado como **público na conta pessoal** (`Victor-9882/FAROL`). Vale atualizar o documento (nova SM / versão) ou transferir para uma organização depois. Com o repo público, a regra de nunca versionar planilhas reais e `.env` fica ainda mais crítica.

---

## 11. Plano de testes (Lab 05 — `FAROL_Testes_v1.pdf`, 28/10/2026)

Cobre RF001–RF022, RN001–RN014, NF001–NF025 (só CASDvest). Aplicação incremental por módulo; ordem: Essenciais primeiro, em especial **RF003, RF010, RF015, RF019** e acesso nominal (**RN013, NF013, NF014**).

### Níveis
| Nível | O que | Responsável | Quando |
|---|---|---|---|
| Unidade | Apuração de falta (RN001, 002, 004, 005), delta e classificação (RN008, 009), validação de linha importada (NF006) | Matheus e Pietro | Junto com o código |
| Integração | Importação → banco → indicadores → regras → painel; agendador; e-mail de ciclo (RF017) em servidor de teste | Eduardo e Yuri | Fim de Ingestão e de Indicadores/Alertas |
| Sistema | Ponta a ponta no celular e desktop; NF001–003, NF010–012, NF013–017 | "Victor (engenheiro de testes)" ⚠️ | Fase de Testes e Validação |
| Aceitação | Com a Direção, sobre dados históricos anonimizados: importação correta, pertinência dos alertas, usabilidade | — | Fim |

### Técnicas
- **Caixa preta:** partição de equivalência, valor-limite, tabela de decisão, transição de estados. Ex.: limiar de queda 30 → testar Δ = −31, −30 (alertam) e −29 (não alerta).
- **Caixa branca:** 100% das decisões nas funções de regra; ≥ 80% das linhas na Ingestão. Ex.: dois ramos de falta justificada (RN002).
- **Caixa cinza:** reimportar arquivo e checar ausência de duplicatas (NF008); Membro pedindo ficha via API → acesso negado (RN013).

### Métodos
- **Automatizado:** unidade + integração a cada entrega (card só vai para Concluído com suíte verde); E2E dos casos centrais; carga com 500 alunos, 3 anos, 20 usuários. Ferramentas: pytest ou Jest, **Playwright**, **k6**.
- **Manual:** exploratório por módulo; Android e iOS reais; sessão de usabilidade com novato só com o guia de 2 páginas; aceitação.
- **Com LLMs:** sugerir casos e entradas extremas, gerar arquivos com erros e o gerador de base, revisar ambiguidades. Saída sempre revisada; resultado esperado vem do requisito; **nenhum dado real enviado**.
- **Estático:** revisão de requisitos, modelagem e código. Já encontrou: falta de histórico de turmas no DER (RN011) e **matrículas em branco no export do Corrija-me** (RN003).

### Dados e critérios
- Base sintética por script: 500 alunos, 5 turmas, 3 anos, feriados, simulados quinzenais, perfis com resultado conhecido (3 faltas na semana, ausente no simulado, mudou de turma).
- **Conclusão de módulo:** 100% dos testes Essenciais aprovados, nenhum defeito grave aberto, metas de cobertura atingidas.
- **Defeitos:** cards no Kanban com severidade crítica/alta/média/baixa. Expor dados nominais a quem não pode = **sempre crítico**.

---

## 12. Entregas da disciplina

| Lab | Tema | Artefato | Data |
|---|---|---|---|
| 01 | Definição de projeto e equipe | `Lab_1_CSI_28.pdf` (proposta FAROL) | 11/08/2026 |
| 02 | Engenharia de Requisitos | `FAROL_DocRequisitos_v1.pdf` | 10/09/2026 |
| 03 | Relatório Descritivo (Entrega Parcial 2) | `FAROL_RelDescritivo_v1.pdf` | — |
| 04 | Controle de Configuração | `FAROL_GConfig.pdf` | 15/10/2026 |
| 05 | Testes | `FAROL_Testes_v1.pdf` | 28/10/2026 |
| Final | Protótipo + documentação + apresentação | — | 1ª semana de exames |

Critérios de sucesso do protótipo (Lab 01): importar corretamente as planilhas reais do CASD, concordância da Direção quanto à pertinência dos alertas sobre dados históricos e usabilidade verificada em sessão com usuário externo.

---

## 13. Pendências e próximos passos

**Com o cliente (Direção do CASD / Olaf)**
- [ ] Levantar a regra de risco já existente na planilha de banco de dados.
- [ ] Definir evasão e o limiar de queda de desempenho.
- [ ] Obter amostras/cópias das planilhas (incluindo anos anteriores) para a pasta restrita.
- [ ] Avaliar viabilidade de automação de P+ e Corrija-me.
- [ ] Validar protótipo de telas.

**Na documentação**
- [ ] Corrigir o responsável do nível *Sistema* no Plano de Testes (Yuri, não Victor).
- [ ] Adicionar histórico de turmas ao DER (RN011).
- [ ] Atualizar o GConfig sobre o repositório (público, conta pessoal, em vez de organização) via SM.

**No desenvolvimento**
- [ ] Definir a stack (linguagem/framework web, banco relacional, hospedagem de baixo custo).
- [ ] Estruturar o monorepo, `.gitignore`, proteção da `main`, CI no GitHub Actions, Docker Compose.
- [ ] Criar o quadro Kanban no GitHub Projects.
- [ ] Gerar a base sintética de testes.
- [ ] Prototipagem → v0.1.0; depois Ingestão (v0.2.0), Indicadores e Alertas (v0.3.0), Intervenções e Relatórios (v0.4.0), entrega final (v1.0.0).

---

## 14. Glossário

| Termo | Significado |
|---|---|
| CASD | Curso Alberto Santos Dumont, o cliente |
| CASDvest / CASDinho | Frentes de vestibular (escopo) e vestibulinho (fora do escopo) |
| DES / RH | Diretorias de Desempenho (notas) e Recursos Humanos (presença) |
| Catraca | Controle de acesso à sede; origem da frequência |
| P+ | Plataforma de simulados |
| Corrija-me | Plataforma de redações |
| Ciclo | 2 semanas entre simulados; unidade de análise de desempenho |
| TRI | Escala de nota padrão ENEM |
| Intervenção | Ação da Direção sobre um aluno sinalizado, com desfecho |
| PEI | Projeto anterior que originou o protótipo de interface |
| SM | Solicitação de Mudança |
| IC | Item de Configuração |
| LB | Linha de base |
