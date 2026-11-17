# Protótipo de telas (fase de Prototipagem)

Protótipo navegável de média fidelidade, para validar com a Direção do CASD (issue #8). Ele parte do protótipo herdado do PEI (Relatório Descritivo, Seção 1.6), adaptado aos requisitos do FAROL. É um arquivo único, [`index.html`](index.html), sem dependências e **só com dados sintéticos**: nove alunos escritos à mão, cada um com uma história para a Direção reconhecer, e o resto do curso (500 alunos em cinco turmas) gerado com semente fixa, para o painel mostrar a forma de um curso real. Os números são os mesmos a cada abertura. O formulário de intervenção funciona, mas nada é gravado: tudo some ao recarregar a página.

## Como abrir

- **No computador:** abra `docs/prototipo/index.html` no navegador. No DevTools, use o modo de dispositivo móvel.
- **No celular, na mesma rede Wi-Fi:** na raiz do repositório, rode `python3 -m http.server 8080 --directory docs/prototipo`. No celular, abra `http://<IP-do-computador>:8080`.

O seletor **Diretor / Membro** no topo existe só no protótipo. Ele mostra o que cada perfil vê (RN013).

## Telas

| Tela | Requisitos | Como chegar |
|---|---|---|
| **Painel inicial**: alertas ativos por tipo; o curso nos quatro grupos (contagem e %), com filtro por ciclo e por turma; plano presença × notas com os índices de −1 a +1 e alternância para tabela; grupos por turma; evolução dos grupos entre ciclos; data da última importação | RF010, RF012 | Tela inicial |
| **Lista de um grupo**: alunos do grupo no ciclo e na turma escolhidos, com os dois índices e os valores de origem | RF012 | 1 toque: cartão do grupo |
| **Lista de alertas** de um tipo, com o motivo de cada um | RF014–RF016, NF004 | 1 toque: cartão do tipo de alerta |
| **Ficha do aluno**: alertas, números do ciclo, grupo e índices com medidor, comparação com a turma, histórico de turmas, trajetória nos quatro grupos, evolução entre ciclos com zoom por área e intervenções | RF011, RF013, RN008, RN011 | 2 toques: alerta ou grupo → aluno, ou 1 toque num ponto do gráfico |
| **Registrar intervenção**: tipo, data, responsável, descrição, alerta associado (opcional) e desfecho (pode ficar para depois) | RF019 | 3 toques: alerta → aluno → botão |

Os alertas e os indicadores do ciclo ficam a no máximo três interações da tela inicial (NF002). O layout é pensado primeiro para o celular (NF001) e acompanha o tema claro ou escuro do aparelho.

## Índices normalizados e os quatro grupos

Como no protótipo do PEI, os dois eixos vão de −1 a +1 e o zero de cada eixo separa quatro grupos. A conta muda só onde um requisito pede. O sistema usa as mesmas contas (`inteligencia/grupos.py`, #92):

| Eixo | Conta | Zero |
|---|---|---|
| **Presença na sede** | `2 · presença − 1`, como o SE do PEI, com a frequência do ciclo (falta justificada conta como presença, RN002): 0% → −1, 50% → 0, 100% → +1 | 50% de presença |
| **Notas nos simulados** | `limitar(z / 2, −1, +1)`, como o SD do PEI, com `z = Δ / σ`: Δ é a nota TRI média do ciclo menos a do último simulado em que o aluno foi avaliado (RN008) e σ é o desvio-padrão dos Δ do curso no ciclo | A nota do último simulado do aluno |

| Grupo | Presença | Notas |
|---|---|---|
| **A · Em dia** | 50% ou mais | igual ou acima do último simulado |
| **B · Nota abaixo** | 50% ou mais | abaixo do último simulado |
| **C · Presença abaixo** | abaixo de 50% | igual ou acima do último simulado |
| **D · Ambas abaixo** | abaixo de 50% | abaixo do último simulado |

Os grupos não usam limiar de alerta: o zero de cada eixo sai da própria conta, sem regra nova. Quem faltou ao simulado (RN009) ou ainda não tem simulado anterior fica fora dos grupos naquele ciclo. As letras e as cores seguem o PEI, mas os rótulos só descrevem a posição (RN012). O perfil Membro vê as contagens e o plano sem nomes; a lista de cada grupo é só do Diretor (RN013).

## O que mudou em relação ao PEI

| PEI | FAROL | Motivo |
|---|---|---|
| SE (engajamento): presença na sede, nos simulados e entrega de redação, com 2·média − 1 | Mesma conta, só com a presença na sede | A entrega de redação aparece na ficha, e a falta no simulado tira o aluno dos grupos naquele ciclo (RN009) |
| SD (desempenho): `limitar(z / 2)`, com z contra a média da turma | Mesma conta, com z calculado sobre o Δ em relação ao último simulado do aluno | A queda é medida pelo próprio histórico (RN008) |
| Quadrantes A–D com rótulos de ação ("Contato urgente") | Grupos A–D só descritivos ("Nota abaixo") | Alertas indicativos, sem classificação dos alunos (RN012) |
| Bloco de "ações sugeridas" em texto | Registro formal de intervenção, com responsável, data e desfecho | RF019, RF020 |
| Flag psicológico, trabalho, transporte, espera de bolsa, ficha psicológica | **Removidos** | Minimização: sem dados de saúde ou socioeconômicos (NF015) |
| "Imprimir / Salvar PDF" | Fora desta fase | RF022 é Desejável |
| Uma tela com lista e gráfico lado a lado | Telas empilhadas para o celular | NF001 |

## Roteiro da validação com a Direção

Registre as respostas em ata no Drive (`00_Gestao/`, IC-03). Pedidos que alterem requisito viram **Solicitação de Mudança**.

1. **Painel:** as três contagens de alerta são as informações certas para abrir o sistema? Falta alguma?
2. **Quatro grupos:** os cartões A–D e o plano presença × notas mostram bem como o curso está? A tabela é mais útil? Os nomes dos grupos são claros?
3. **Índices:** o zero da presença em 50%, como no PEI, separa bem quem está se afastando da sede? Se a Direção preferir outro valor (por exemplo, 75%), isso vira Solicitação de Mudança, porque cria um limiar novo.
4. **Motivo do alerta:** o texto ("3 faltas não justificadas na semana de 18/05") é suficiente para agir?
5. **Limiares (RF018):** 3 faltas na semana e 75% de frequência no ciclo são pontos de partida razoáveis? Quantos pontos de queda de TRI devem gerar alerta? (Questões em aberto 1–3 do Documento de Requisitos.)
6. **Ficha:** a evolução entre ciclos e o zoom por área bastam? A comparação com a média da turma é útil?
7. **Intervenção:** os tipos (contato, conversa, encaminhamento) e os desfechos (resolvido, em acompanhamento, sem retorno) cobrem o que acontece na prática?
8. **Perfil Membro:** ver só as contagens, os grupos por turma e o plano sem nomes atende aos membros do Desenvolvimento?
9. **Celular:** os textos e os botões têm tamanho bom? Alguma tela exige rolagem demais?
10. **Auxílios (RF021):** onde a Direção espera ver o acompanhamento dos alunos beneficiados por auxílios?
