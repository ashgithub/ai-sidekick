#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"
source "${SCRIPT_DIR}/common_env.sh"

CONFIG_PATH="${AI_TOOLS_WEB_PANEL_CONFIG:-config/codex_web_panel.yaml}"
CONFIG_JSON="$(
  AI_TOOLS_WEB_PANEL_CONFIG="${CONFIG_PATH}" "${SCRIPT_DIR}/codex_web_panel_config_json.sh"
)"
PORT="$(
  printf '%s' "${CONFIG_JSON}" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["server"]["port"])'
)"
BASE_URL="http://127.0.0.1:${PORT}"

RESPONSE="$(
  /usr/bin/curl --silent --show-error --fail \
  -X POST \
  -H "Content-Type: application/json" \
  --data '{}' \
  "${BASE_URL}/api/panel/show"
)" || {
  echo "Codex sidekick is not running." >&2
  echo "Start it with: ./scripts/start_web_panel_daemon.sh --restart" >&2
  exit 1
}

if printf '%s' "${RESPONSE}" | /usr/bin/python3 -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("visible") is True else 1)'; then
  exit 0
fi

echo "Codex sidekick is running without a native window." >&2
echo "Restart it with: ./scripts/start_web_panel_daemon.sh --restart" >&2
exit 1
