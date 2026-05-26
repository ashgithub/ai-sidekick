#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"
source "${SCRIPT_DIR}/common_env.sh"

CONFIG_PATH="${AI_TOOLS_WEB_PANEL_CONFIG:-config/codex_web_panel.yaml}"

exec ${AI_TOOLS_PYTHON_BIN} -m ai_tools.web_panel.app --config "${CONFIG_PATH}" --show-on-start
