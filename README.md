# AI Sidekick

Python-based local Sidekick for resident Codex workflows, text tools, and Slack shortcut handoff.

## Tools

- Resident Codex Web Panel: local sidekick for shortcut-driven Codex runs.
- Sidekick text shortcuts and diagnostic CLI: see `docs/ai-text-tools.md`.
- Codex NL-to-shell shortcut, `ctrl+option+command+/`: see `docs/codex-nl-shell-shortcut.md`.
- Slack Codex workflow, `ctrl+option+command+right`: see `docs/slack-codex-workflow.md`.

## Resident Codex Web Panel

The repository now includes a Python-only Codex web panel POC:

1. A resident local bridge backed by `codex app-server`.
2. A compact sidekick panel for live progress, clear outcomes, approvals, and optional debug inspection.
3. Loopback ingress so keyboard shortcuts can submit work to a bridge you started explicitly.

Human-facing entry points:

```bash
./bin/sidekick
./bin/sidekick-check
```

For shortcut testing, start `./bin/sidekick` in a terminal and leave it running. The Slack hotkey does not auto-start the bridge; if the bridge is not reachable, Hammerspoon shows the script path to run.

Configuration lives in `config/codex_web_panel.yaml`. It controls the loopback port, panel visibility, native macOS notifications, function-key panel hotkey, Codex model/thread defaults, Slack prompt path, Sidekick text shortcut profiles, and the stale-source threshold for latest `@codex` lookup. Sidekick text profile prompts are plain Markdown files under `prompts/`. The default Codex working directory is `~/tmp/codex_ai_tools`, so sidekick proofread/explain threads do not appear under the current project unless you change `codex.cwd`. The default panel toggle hotkey is `F5`; change `panel.open_hotkey` if browser refresh conflicts with your muscle memory.

The bridge exposes `GET /healthz` for process liveness and `GET /readyz` for shortcut readiness. Readiness verifies the Codex binary is executable before Hammerspoon submits work. Run state is intentionally ephemeral: the bridge keeps only the current invocation in memory, and a restart clears it.

`bin/sidekick` starts the bridge and a hidden native pywebview sidekick. Press `F5` to toggle it. The panel show/toggle shell scripts are app-facing helpers under `scripts/internal/`, not normal user commands. Use `./bin/sidekick --bridge-only` only when you explicitly want HTTP ingress without a native window.

The sidekick shows only the current invocation by default: outcome banner, progress phases, readable answer, Abort while work is running, Close to hide the panel, steering/continue composer, and approval actions. Prompt, raw stream, tool calls, and trace are collapsed into debug sections. Slack source lookup outcomes are explicit: `not_found` and `stale_source` no longer appear as generic successful completions.

If port `8765` is already occupied, the launcher prints a diagnostic instead of a Python traceback. To replace the existing listener and stay on the configured port, run `./bin/sidekick --restart`.

Panel visibility is source-neutral and configurable. The current POC default is `panel.visibility: always`, so an accepted shortcut opens the panel for immediate feedback. Switch to `attention` later if you only want it to open for approvals or failures. A one-off launcher override is also available:

```bash
./bin/sidekick --restart --panel-visibility attention
```

Current integration scope:
1. Slack hotkey ingress posts to `/ingest/slack`.
2. The sidekick can steer the active turn, continue the current thread, or start a new task.
3. The Sidekick diagnostic CLI submits explicit structured text-tool work to `/api/ai-tools`. Hammerspoon posts only `{app, text, interaction}` to `/api/shortcut`; the bridge resolves app profiles, prompt files, thread reuse, panel behavior, and shortcut results before Hammerspoon pastes reviewed output back into the source app. Slack and email wait for sidekick review before paste-back. Safari, Chrome, Terminal, iTerm2, Ghostty, Codex, and Code open Ask mode for explain/copy workflows. Any Sidekick-edited AI output must first go through `Review edits` before it can be applied.
4. The legacy Tk client has been removed; Sidekick is the only supported UI path.
5. The zsh command helper submits to the sidekick through `bin/codex-nl-shell` and still inserts the generated command for review before Enter.

Sidekick text tools use in-memory per-tool reusable Codex threads when submitted with `intent: reuse`. This avoids a fresh `thread/start` for each proofread/explain shortcut while preserving the ephemeral run model: only the current invocation is shown. Reusable threads reset on daemon restart, after `codex.reusable_thread_max_turns` turns, or after `codex.reusable_thread_max_age_minutes`.

## Development

Run the full local validation pipeline:

```bash
./bin/sidekick-check
```

It runs:
1. `ruff check`
2. `compileall`
3. `pytest`

Additional implementation notes are in `docs/development.md`. Terminal presentation decks live under `docs/presentations/`.
