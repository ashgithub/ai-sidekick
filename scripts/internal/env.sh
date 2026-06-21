#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"

if [[ -n "${AI_SIDEKICK_USE_LOCAL_VENV:-}" && -x "${VENV_PYTHON}" ]]; then
  export AI_TOOLS_PYTHON_BIN="${VENV_PYTHON}"
else
  export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/ai-sidekick-uv-cache}"
  export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${TMPDIR:-/tmp}/ai-sidekick-venv}"
  export AI_TOOLS_PYTHON_BIN="/opt/homebrew/bin/uv run python"
fi
