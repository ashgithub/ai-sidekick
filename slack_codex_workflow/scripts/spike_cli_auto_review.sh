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

Captured by: CLI auto-review spike
Captured at: ${CAPTURED_AT}
Source app: CLI spike
Bundle id: unavailable
Window title: CLI auto-review spike without Slack source
Captured text capture mode: none
Captured text selection: empty
Source conversation: none; do not post a source status message for this spike.

Captured text:

Instructions:
Use Slack app only. Fail immediately if the Slack connector is unavailable.
Start every Slack message you send or edit with [from codex :bot:].
Keep the wand status message and do not use reactions.
Search for Ashish's newest @codex message from the last five minutes.
If no recent @codex message is found, stop with the worker prompt's not-found message.
Do not reply in a source conversation; this synthetic spike has no source Slack conversation.
Marker for diagnostic logs only: ${MARKER}
PAYLOAD
)"

echo "Running Codex CLI auto-review spike."
echo "Marker: ${MARKER}"

{
  cat "${PROMPT_FILE}"
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
