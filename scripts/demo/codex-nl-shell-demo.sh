#!/usr/bin/env bash
set -euo pipefail

REQUEST="${*:-find the 20 largest json files under this repo}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Request: ${REQUEST}"
echo "Working directory: ${PWD}"
echo
echo "Invoking the resident sidekick-backed zsh command helper..."
echo

"${ROOT_DIR}/bin/codex-nl-shell" "${REQUEST}"

echo
echo "This demo does not execute the generated command."
