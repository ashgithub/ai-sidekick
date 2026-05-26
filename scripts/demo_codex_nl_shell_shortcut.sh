#!/usr/bin/env bash
set -euo pipefail

REQUEST="${*:-find the 20 largest json files under this repo}"
MODEL="${CODEX_NL_MODEL:-gpt-5.4-mini}"
TMP_FILE="$(mktemp -t codex-nl-shell-demo.XXXXXX)"
ERR_FILE="${TMP_FILE}.err"

cleanup() {
  rm -f "${TMP_FILE}" "${ERR_FILE}"
}
trap cleanup EXIT

if ! command -v codex >/dev/null 2>&1; then
  echo "codex CLI not found on PATH" >&2
  exit 1
fi

echo "Request: ${REQUEST}"
echo "Model: ${MODEL}"
echo "Working directory: ${PWD}"
echo
echo "Invoking the same codex exec shape used by ~/.zsh/widgets/codex-nl-shell.zsh..."

if ! codex exec \
  --ephemeral \
  --sandbox read-only \
  --skip-git-repo-check \
  -m "${MODEL}" \
  --cd "${PWD}" \
  -o "${TMP_FILE}" \
  "Convert this natural language request into one safe zsh command for macOS/Linux. Return only the command, with no Markdown, no explanation, and no execution. Prefer rg, fd, bat, zoxide, and safe read-only commands when they fit. Request: ${REQUEST}" \
  >/dev/null 2>"${ERR_FILE}"; then
  cp "${ERR_FILE}" /tmp/codex-nl-shell-last.err
  echo "Codex failed; stderr copied to /tmp/codex-nl-shell-last.err" >&2
  exit 1
fi

if [[ ! -s "${TMP_FILE}" ]]; then
  echo "Codex returned an empty command" >&2
  exit 1
fi

GENERATED="$(<"${TMP_FILE}")"
GENERATED="${GENERATED//$'\r'/}"
GENERATED="${GENERATED#"${GENERATED%%[![:space:]]*}"}"
GENERATED="${GENERATED%"${GENERATED##*[![:space:]]}"}"
GENERATED="${GENERATED#\`\`\`zsh$'\n'}"
GENERATED="${GENERATED#\`\`\`sh$'\n'}"
GENERATED="${GENERATED#\`\`\`bash$'\n'}"
GENERATED="${GENERATED#\`\`\`$'\n'}"
GENERATED="${GENERATED%$'\n'\`\`\`}"

echo
echo "Generated command:"
printf '%s\n' "${GENERATED}"
echo
echo "This demo does not execute the generated command."
