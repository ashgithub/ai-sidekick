#!/usr/bin/env bash
set -euo pipefail

# Manually submit text work to the resident Codex sidekick.
#
# Sample invocations:
#   # Ask / explain default (auto nudge)
#   ./scripts/dev/sidekick-submit-text.sh --text "What is the difference between TCP and UDP?"
#
#   # Slack-proofread nudge
#   ./scripts/dev/sidekick-submit-text.sh --app slack --nudge slack --text "hi team pls review the doc by tomrw"
#
#   # Commands nudge
#   ./scripts/dev/sidekick-submit-text.sh --nudge commands --text "find all .py files modified in last 24 hours"
#
#   # Pipe stdin text
#   echo "pls fix grammar" | ./scripts/dev/sidekick-submit-text.sh --nudge proofread

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

exec /opt/homebrew/bin/uv run python -m ai_tools.ingress.client --repo-root "${ROOT_DIR}" "$@"
