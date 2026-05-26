#!/usr/bin/env bash
set -euo pipefail

REQUEST="${*:-find the 20 largest json files under this repo}"

echo "Request: ${REQUEST}"
echo "Working directory: ${PWD}"
echo
echo "Invoking the resident sidekick-backed zsh command helper..."
echo

./scripts/codex_nl_shell_sidekick.sh "${REQUEST}"

echo
echo "This demo does not execute the generated command."
