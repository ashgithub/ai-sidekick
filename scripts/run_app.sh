#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--tk" ]]; then
  echo "The legacy Tk client has been removed. Use ./bin/sidekick or ./scripts/dev/sidekick-submit-text.sh." >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${ROOT_DIR}/scripts/dev/sidekick-submit-text.sh" "$@"
