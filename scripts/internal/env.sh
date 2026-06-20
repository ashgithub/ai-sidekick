#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"

if [[ -x "${VENV_PYTHON}" ]]; then
  export AI_TOOLS_PYTHON_BIN="${VENV_PYTHON}"
else
  export UV_CACHE_DIR="${ROOT_DIR}/.cache/uv"
  export AI_TOOLS_PYTHON_BIN="/opt/homebrew/bin/uv run python"
fi
