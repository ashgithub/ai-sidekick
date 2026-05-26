#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_DIR="${HOME}/work/code/python/ai_tools/slack_codex_workflow"
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

MARKER="SLACK_CODEX_CLI_AUTO_REVIEW_SPIKE_$(date +%Y%m%dT%H%M%S)"
CAPTURED_AT="$(date +%Y-%m-%dT%H:%M:%S%z)"

HOTKEY_PAYLOAD="$(cat <<PAYLOAD
Slack Codex hotkey task

Request time: ${CAPTURED_AT}
Task resolver: latest @codex message from Ashish
Marker for diagnostic logs only: ${MARKER}
PAYLOAD
)"

echo "Running Codex CLI auto-review spike."
echo "Marker: ${MARKER}"

{
  cat "${PROMPT_FILE}"
  printf '\n\n## Runtime Resolver Settings\n\n'
  printf 'Maximum source age: 30 minutes\n'
  printf '\n\n## Captured Hotkey Payload\n\n'
  printf '%s\n' "${HOTKEY_PAYLOAD}"
} | "${CODEX_BIN}" exec \
  --ephemeral \
  --skip-git-repo-check \
  --sandbox workspace-write \
  --config 'approval_policy="on-request"' \
  --config 'approvals_reviewer="auto_review"' \
  -C "${WORKFLOW_DIR}" \
  -
