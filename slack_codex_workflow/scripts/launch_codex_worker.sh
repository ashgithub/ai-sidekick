#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_DIR="${HOME}/work/code/python/ai-sidekick/slack_codex_workflow"
PROMPT_FILE="${WORKFLOW_DIR}/prompts/codex_worker.md"
CODEX_BIN="${CODEX_BIN:-/opt/homebrew/bin/codex}"

if [[ ! -x "${CODEX_BIN}" ]]; then
  echo "codex binary not found or not executable: ${CODEX_BIN}" >&2
  exit 127
fi

if [[ ! -f "${PROMPT_FILE}" ]]; then
  echo "worker prompt not found: ${PROMPT_FILE}" >&2
  exit 1
fi

HOTKEY_PAYLOAD="${1:-}"

{
  cat "${PROMPT_FILE}"
  printf '\n\n## Captured Hotkey Payload\n\n'
  printf '%s\n' "${HOTKEY_PAYLOAD}"
} | "${CODEX_BIN}" exec \
  --ephemeral \
  --skip-git-repo-check \
  --sandbox workspace-write \
  --config 'approval_policy="on-request"' \
  -C "${WORKFLOW_DIR}" \
  -
