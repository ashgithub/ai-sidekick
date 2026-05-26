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

exec /usr/bin/open "http://127.0.0.1:${PORT}/"
