#!/usr/bin/env bash
set -euo pipefail

# Submit AI Tools work to the resident Codex sidekick by default.
# Use --tk to launch the legacy Tk GUI fallback.
#
# Sample invocations:
#   # Ask / explain default (auto nudge)
#   ./scripts/run_app.sh --text "What is the difference between TCP and UDP?"
#
#   # Slack-proofread nudge
#   ./scripts/run_app.sh --app slack --nudge slack --text "hi team pls review the doc by tomrw"
#
#   # Commands nudge
#   ./scripts/run_app.sh --nudge commands --text "find all .py files modified in last 24 hours"
#
#   # Pipe stdin text
#   echo "pls fix grammar" | ./scripts/run_app.sh --nudge proofread

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ "${1:-}" == "--tk" ]]; then
  shift
  exec /opt/homebrew/bin/uv run clients/multi_tool_client.py "$@"
fi

exec /opt/homebrew/bin/uv run python -m ai_tools.ingress.client --repo-root "${ROOT_DIR}" "$@"
