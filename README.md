# AI Tools

Python-based local productivity tools for resident Codex workflows, text tools, and Slack shortcut handoff.

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

`start_web_panel_daemon.sh` runs the bridge without opening the webview, but it still serves the sidekick at `http://127.0.0.1:8765/`. Run `./scripts/open_web_panel.sh` to inspect the current invocation in your browser. Use `./scripts/run_web_panel.sh` only when you specifically want the pywebview shell. Do not run both on the same port at the same time.

The sidekick shows only the current invocation by default: outcome banner, progress phases, response, and approval actions. Prompt, trace, and manual submission are collapsed into debug sections. Slack source lookup outcomes are explicit: `not_found` and `stale_source` no longer appear as generic successful completions.

If port `8765` is already occupied, the launcher prints a diagnostic instead of a Python traceback. To replace the existing listener and stay on the configured port, run `./scripts/start_web_panel_daemon.sh --restart`.

Panel visibility is source-neutral and configurable. The current POC default is `panel.visibility: always`, so an accepted shortcut opens the panel for immediate feedback. Switch to `attention` later if you only want it to open for approvals or failures. A one-off launcher override is also available:

```bash
./scripts/start_web_panel_daemon.sh --restart --panel-visibility attention
```

Current integration scope:
1. Slack hotkey ingress posts to `/ingest/slack`.
2. The web panel can submit manual test runs through `/api/runs/manual`.
3. The existing Tk `ai_tools` client and zsh widget do not submit to this bridge yet.

## Native Deep Agents (Agentic)

The app uses a single universal workflow:

1. One input workspace in the UI.
2. Deep Agent receives all skills from `skills/*/SKILL.md`.
3. `AGENTS.md` is loaded as global memory.
4. A soft nudge (`--nudge`, app context) selects expected output schema.
5. The agent decides which skill/tool to use.
6. Deep Agents backend is explicitly `FilesystemBackend(root_dir=<project>)`.
7. Runtime injects an explicit task nudge prompt from `config.yaml -> agentic_routing.nudge_prompts`.

## Shared Output Schemas (minimal)

1. `SingleText` -> `text`
2. `TextPair` -> `corrected`, `rewritten`
3. `Alternatives` -> `alternatives[]` where item is `value`, `explanation`

## Run from command line

```bash
./scripts/run_app.sh --text "Explain CAP theorem"
./scripts/run_app.sh --nudge slack --app slack --text "hi team pls review by tomrw"
./scripts/run_app.sh --nudge commands --text "list large files in current directory"
```

Legacy flags remain accepted for compatibility:

```bash
./scripts/run_app.sh --tab Proofread --app slack --text "quick draft message"
```

## Refresh models

Use `Refresh Models` button in the GUI.

Refresh runs only through `skills/refresh-llms/scripts/refresh_llms.sh` via runtime action `refresh_models`.

## Window placement

When `--window-x/--window-y` are missing, the app starts centered in the visible desktop bounds.

## Validation / test script

Run the full local validation pipeline:

```bash
./scripts/test_app.sh
```

It runs:
1. `ruff check`
2. `compileall`
3. `pytest`

## Dead code audit (current)

This refactor removed obsolete paths:
1. Deterministic tab/app skill routing path.
2. Resolved payload blob and synthetic “execute skill with payload” prompt path.
3. Unused `preview_instruction` runtime API.
4. Unused deterministic `RouteError` export.
5. Unused `commands` config section in settings model.
