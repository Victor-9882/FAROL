# Protótipo de telas (fase de Prototipagem)

Protótipo navegável de média fidelidade, para validar com a Direção do CASD (issue #8). Ele parte do protótipo herdado do PEI (Relatório Descritivo, Seção 1.6), adaptado aos requisitos do FAROL. É um arquivo único, [`index.html`](index.html), sem dependências e **só com dados sintéticos**. O formulário de intervenção funciona, mas nada é gravado: tudo some ao recarregar a página.

## Como abrir

- **No computador:** abra `docs/prototipo/index.html` no navegador. No DevTools, use o modo de dispositivo móvel.
- **No celular, na mesma rede Wi-Fi:** na raiz do repositório, rode `python3 -m http.server 8080 --directory docs/prototipo`. No celular, abra `http://<IP-do-computador>:8080`.

O seletor **Diretor / Membro** no topo existe só no protótipo. Ele mostra o que cada perfil vê (RN013).

## Telas

| Tela | Requisitos | Como chegar |
|---|---|---|
| **Painel inicial**: alertas ativos por tipo, dispersão frequência × desempenho com filtro por ciclo e alternância para tabela, situação das turmas, data da última importação | RF010, RF012 | Tela inicial |
| **Lista de alertas** de um tipo, com o motivo de cada um | RF014–RF016, NF004 | 1 toque: cartão do tipo de alerta |
| **Ficha do aluno**: alertas, números do ciclo, Δ em relação à própria média, comparação com a turma, histórico de turmas, evolução entre ciclos com zoom por área e intervenções | RF011, RF013, RN008, RN011 | 2 toques: alerta → aluno, ou 1 toque num ponto do gráfico |
| **Registrar intervenção**: tipo, data, responsável, descrição, alerta associado (opcional) e desfecho (pode ficar para depois) | RF019 | 3 toques: alerta → aluno → botão |

Os alertas e os indicadores do ciclo ficam a no máximo três interações da tela inicial (NF002). O layout é pensado primeiro para o celular (NF001) e acompanha o tema claro ou escuro do aparelho.

## O que mudou em relação ao PEI

| PEI | FAROL | Motivo |
|---|---|---|
| Escores SE (engajamento) e SD (desempenho), de −1 a +1 | Frequência (%) e Δ da nota TRI em relação à própria média | Indicadores interpretáveis (NF021); a queda é medida pelo próprio histórico (RN008) |
| Quadrantes A–D com rótulos de ação ("Contato urgente") | Quadrantes só descritivos ("baixa frequência e queda") | Alertas indicativos, sem classificação dos alunos (RN012) |
| Bloco de "ações sugeridas" em texto | Registro formal de intervenção, com responsável, data e desfecho | RF019, RF020 |
| Flag psicológico, trabalho, transporte, espera de bolsa, ficha psicológica | **Removidos** | Minimização: sem dados de saúde ou socioeconômicos (NF015) |
| "Imprimir / Salvar PDF" | Fora desta fase | RF022 é Desejável |
| Uma tela com lista e gráfico lado a lado | Telas empilhadas para o celular | NF001 |

## Roteiro da validação com a Direção

Registre as respostas em ata no Drive (`00_Gestao/`, IC-03). Pedidos que alterem requisito viram **Solicitação de Mudança**.

1. **Painel:** as três contagens de alerta são as informações certas para abrir o sistema? Falta alguma?
2. **Dispersão:** o gráfico frequência × Δ desempenho ajuda a decidir com quem conversar? A tabela é mais útil?
3. **Motivo do alerta:** o texto ("3 faltas não justificadas na semana de 18/05") é suficiente para agir?
4. **Limiares (RF018):** 3 faltas na semana e 75% de frequência no ciclo são pontos de partida razoáveis? Quantos pontos de queda de TRI devem gerar alerta? (Questões em aberto 1–3 do Documento de Requisitos.)
5. **Ficha:** a evolução entre ciclos e o zoom por área bastam? A comparação com a média da turma é útil?
6. **Intervenção:** os tipos (contato, conversa, encaminhamento) e os desfechos (resolvido, em acompanhamento, sem retorno) cobrem o que acontece na prática?
7. **Perfil Membro:** ver só as contagens e a situação das turmas atende aos membros do Desenvolvimento?
8. **Celular:** os textos e os botões têm tamanho bom? Alguma tela exige rolagem demais?
9. **Auxílios (RF021):** onde a Direção espera ver o acompanhamento dos alunos beneficiados por auxílios?
