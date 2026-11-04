#!/usr/bin/env bash
# Cria (ou atualiza) as labels do FAROL no repositório.
# Pode ser executado mais de uma vez sem duplicar nada.
# Não apaga as labels padrão do GitHub.
#
# Requisitos: GitHub CLI (gh) autenticado com permissão de escrita no repo.
#   gh auth login
# Uso:
#   ./scripts/criar_labels.sh ORGANIZACAO/farol

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: $0 ORGANIZACAO/REPOSITORIO" >&2
  exit 1
fi

REPO="$1"

if ! command -v gh >/dev/null 2>&1; then
  echo "Erro: GitHub CLI (gh) não encontrado. Instale em https://cli.github.com/" >&2
  exit 1
fi

# nome|cor (hex sem #)|descrição
LABELS=(
  # Tipo de issue
  "tarefa|1D76DB|Implementação prevista no Documento de Requisitos"
  "solicitacao-mudanca|5319E7|Solicitação de Mudança em item de linha de base (GConfig, Seção 5)"
  "defeito|D73A4A|Comportamento que viola um requisito"
  "auditoria|0E8A16|Auditoria de linha de base antes de uma tag (GConfig, Seção 7)"
  "dependencias|BFD4F2|Atualização de dependências (Dependabot)"

  # Severidade de defeitos (Plano de Testes)
  "sev:critica|B60205|Defeito crítico — inclui qualquer exposição de dados nominais"
  "sev:alta|D93F0B|Defeito de severidade alta"
  "sev:media|FBCA04|Defeito de severidade média"
  "sev:baixa|C2E0C6|Defeito de severidade baixa"

  # Estado da Solicitação de Mudança (GConfig, Figura 2)
  "sm:em-analise|C5DEF5|SM aguardando análise de impacto"
  "sm:aguardando-direcao|F9D0C4|SM que altera requisito; aguardando validação da Direção do CASD"
  "sm:aprovada|0E8A16|SM aprovada pelo gerente de configuração"
  "sm:rejeitada|6A737D|SM rejeitada (justificativa no comentário)"
)

for entrada in "${LABELS[@]}"; do
  IFS='|' read -r nome cor descricao <<< "$entrada"
  gh label create "$nome" --repo "$REPO" --color "$cor" --description "$descricao" --force
done

echo "Labels criadas/atualizadas em $REPO."
