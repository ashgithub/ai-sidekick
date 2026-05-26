# AI Tools

Python-based local productivity tools for resident Codex workflows, text tools, and Slack shortcut handoff.

## Tools

- Resident Codex Web Panel: local sidekick for shortcut-driven Codex runs.
- AI Text Tools GUI and CLI: see `docs/ai-text-tools.md`.
- Codex NL-to-shell shortcut, `ctrl+option+command+/`: see `docs/codex-nl-shell-shortcut.md`.
- Slack Codex workflow, `ctrl+option+command+right`: see `docs/slack-codex-workflow.md`.

## Resident Codex Web Panel

The repository now includes a Python-only Codex web panel POC:

1. A resident local bridge backed by `codex app-server`.
2. A compact sidekick panel for live progress, clear outcomes, approvals, and optional debug inspection.
3. Loopback ingress so keyboard shortcuts can submit work to a bridge you started explicitly.

Developer entry points:

```bash
./scripts/start_web_panel_daemon.sh
./scripts/run_web_panel.sh
./scripts/open_web_panel.sh
```

For shortcut testing, start `./scripts/start_web_panel_daemon.sh` in a terminal and leave it running. The Slack hotkey does not auto-start the bridge; if the bridge is not reachable, Hammerspoon shows the script path to run.

Configuration lives in `config/codex_web_panel.yaml`. It controls the loopback port, panel visibility, function-key panel hotkey, Codex model/thread defaults, Slack prompt path, and the stale-source threshold for latest `@codex` lookup. The default panel hotkey is `F5`; change `panel.open_hotkey` if browser refresh conflicts with your muscle memory.

The bridge exposes `GET /healthz` for process liveness and `GET /readyz` for shortcut readiness. Readiness verifies the Codex binary is executable before Hammerspoon submits work. Run state is intentionally ephemeral: the bridge keeps only the current invocation in memory, and a restart clears it.

`start_web_panel_daemon.sh` starts the bridge and a hidden native pywebview sidekick. Run `./scripts/open_web_panel.sh` or press `F5` to show/focus that sidekick. Use `./scripts/start_web_panel_daemon.sh --bridge-only` only when you explicitly want HTTP ingress without a native window.

The sidekick shows only the current invocation by default: outcome banner, progress phases, readable answer, steering/continue composer, and approval actions. Prompt, raw stream, tool calls, and trace are collapsed into debug sections. Slack source lookup outcomes are explicit: `not_found` and `stale_source` no longer appear as generic successful completions.

If port `8765` is already occupied, the launcher prints a diagnostic instead of a Python traceback. To replace the existing listener and stay on the configured port, run `./scripts/start_web_panel_daemon.sh --restart`.

Panel visibility is source-neutral and configurable. The current POC default is `panel.visibility: always`, so an accepted shortcut opens the panel for immediate feedback. Switch to `attention` later if you only want it to open for approvals or failures. A one-off launcher override is also available:

```bash
./scripts/start_web_panel_daemon.sh --restart --panel-visibility attention
```

Current integration scope:
1. Slack hotkey ingress posts to `/ingest/slack`.
2. The sidekick can steer the active turn, continue the current thread, or start a new task.
3. `ai_tools` CLI/Hammerspoon text processing submits to `/api/invoke` by default.
4. The legacy Tk client is still available with `./scripts/run_app.sh --tk`.
5. The zsh command helper submits to the sidekick through `scripts/codex_nl_shell_sidekick.sh` and still inserts the generated command for review before Enter.

## Development

Run the full local validation pipeline:

```bash
./scripts/test_app.sh
```

It runs:
1. `ruff check`
2. `compileall`
3. `pytest`

Additional implementation notes are in `docs/development.md`. Terminal presentation decks live under `docs/presentations/`.
