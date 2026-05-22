#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_DIR="${HOME}/work/code/python/ai_tools/slack_codex_workflow"
PROMPT_FILE="${WORKFLOW_DIR}/prompts/codex_worker.md"
CODEX_BIN="${CODEX_BIN:-/opt/homebrew/bin/codex}"
HS_BIN="${HS_BIN:-/Applications/Hammerspoon.app/Contents/Frameworks/hs/hs}"
MODE="${1:-copy}"

if [[ "${MODE}" != "copy" && "${MODE}" != "--submit" ]]; then
  echo "usage: $0 [copy|--submit]" >&2
  exit 2
fi

if [[ ! -x "${CODEX_BIN}" ]]; then
  echo "codex binary not found or not executable: ${CODEX_BIN}" >&2
  exit 127
fi

if [[ ! -f "${PROMPT_FILE}" ]]; then
  echo "worker prompt not found: ${PROMPT_FILE}" >&2
  exit 1
fi

if [[ "${MODE}" == "--submit" && ! -x "${HS_BIN}" ]]; then
  echo "Hammerspoon IPC binary not found or not executable: ${HS_BIN}" >&2
  exit 127
fi

MARKER="SLACK_CODEX_APP_SPIKE_$(date +%Y%m%dT%H%M%S)"
CAPTURED_AT="$(date +%Y-%m-%dT%H:%M:%S%z)"

HOTKEY_PAYLOAD="$(cat <<PAYLOAD
Slack Codex hotkey task

Captured by: Hammerspoon spike
Captured at: ${CAPTURED_AT}
Source app: Slack
Bundle id: com.tinyspeck.slackmacgap
Window title: Direct Message with Ashish Saagarwalla (self DM)
Slack context type: DM channel
Source permalink: unavailable in this synthetic Codex.app spike

Captured text:
${MARKER}
This is a Slack Codex workflow Codex.app invocation spike from a synthetic self-DM capture.
Expected behavior: search for the newest @codex message from Ashish in the last five minutes and stop with the not-found message if none exists.
Do not reply in the DM because this synthetic test payload has no source permalink.

Instructions:
Use Slack app only. Fail immediately if the Slack connector is unavailable.
Start every Slack message you send or edit with [from codex :bot:].
Keep the wand status message and do not use reactions.
Search for the newest @codex message from Ashish in the last five minutes.
If no recent @codex message is found, stop with the not-found message from the worker prompt.
Marker for diagnostic logs only: ${MARKER}
PAYLOAD
)"

{
  cat "${PROMPT_FILE}"
  printf '\n\n## Captured Hotkey Payload\n\n'
  printf '%s\n' "${HOTKEY_PAYLOAD}"
} | pbcopy

"${CODEX_BIN}" app "${WORKFLOW_DIR}" >/dev/null 2>&1 &

echo "Prepared Codex.app spike prompt."
echo "Marker: ${MARKER}"
echo "Workspace: ${WORKFLOW_DIR}"

if [[ "${MODE}" == "copy" ]]; then
  echo "Prompt copied to clipboard. Paste it into Codex.app when the workspace opens."
  exit 0
fi

sleep 1.5

submit_result="$("${HS_BIN}" -c 'if not slackCodexSubmitPromptFromClipboard then return "missing slackCodexSubmitPromptFromClipboard; reload Hammerspoon" end; slackCodexSubmitPromptFromClipboard(); return "requested"')"
echo "${submit_result}"
if [[ "${submit_result}" == *"missing slackCodexSubmitPromptFromClipboard"* ]]; then
  exit 1
fi

echo "Requested Hammerspoon to submit the prompt to a new Codex.app chat."
echo "Approve Slack MCP writes in Codex.app when prompted."
