# Slack Codex Workflow

Hotkey-driven Slack-to-Codex workflow for turning Slack messages into Codex work items.

## Contract

- Use Slack to resolve the source task and post replies/status updates.
- Use other connectors when the requested work requires them.
- Every Slack message from the worker starts with `[from codex :bot:]`.
- The wand status message stays in the source thread.
- No reactions are used.
- The latest `@codex` message from Ashish is the queue.
- `#codex-work` is not used.
- No local queue is used.
- Task state is tracked in the source Slack thread with a source status message for visible milestone updates.

## Hotkey

`ctrl+option+command+right`

The hotkey posts minimal resolver metadata to the local resident Codex bridge. Start the bridge first with `scripts/start_web_panel_daemon.sh`; Hammerspoon does not auto-start it. Hammerspoon checks `GET /readyz` before submitting work. If the local bridge is unavailable or not ready, Hammerspoon stops and shows the script path to run instead of falling back to Codex.app. It does not copy selected Slack text or read existing clipboard content. Hammerspoon shows `Checking Codex bridge...` while checking readiness and `Queued Codex task` when the local bridge accepts the request.

Panel-toggle hotkey: `F5` by default. Configure this in `config/codex_web_panel.yaml` under `panel.open_hotkey`. This hotkey toggles the local panel; it does not submit Slack work.

The panel is intentionally a compact native sidekick, not a dashboard or browser tab. It has Rewrite and Ask modes, shows one main task canvas, and keeps progress, prompt, raw output, tools, and trace details behind a collapsed Details disclosure. Approvals appear only when a run needs them.

## Flow

1. Post a Slack message that starts with or contains `@codex`.
2. Start `scripts/start_web_panel_daemon.sh` in a terminal if it is not already running.
3. Press `ctrl+option+command+right`.
4. Hammerspoon sends only request time and resolver intent.
5. Hammerspoon checks `http://127.0.0.1:<port>/readyz`.
6. Hammerspoon posts the captured payload to `http://127.0.0.1:<port>/ingest/slack` only when the bridge reports ready.
7. If the bridge is unavailable, not ready, or rejects the POST, Hammerspoon stops and shows the script path to run.
8. If the local bridge accepts the request, it starts or resumes the resident Codex runtime.
9. The panel opens immediately when `panel.visibility: always`; with `attention`, it stays hidden unless approvals or failures need attention.
10. Codex verifies Slack MCP is available.
11. Codex searches for Ashish's latest `@codex` message without a hard `after` filter.
12. If no match is found, Codex stops with the not-found message.
13. If the latest match is older than `slack.latest_message_max_age_minutes`, Codex stops with the stale-source message.
14. If a non-stale match is found, Codex reads that source thread.
15. Codex posts a source status thread reply that starts with `[from codex :bot:] :magic_wand: Found recent @codex task`.
16. Codex edits that same source status message for important milestones.
17. Codex completes the work, replies in the original Slack conversation when appropriate, and updates the source status message to completed or failed.

## Bridge Readiness

`GET /healthz` reports only that the HTTP process is alive. `GET /readyz` is the shortcut gate: it returns JSON and HTTP 200 only when the configured Codex binary is executable. Hammerspoon uses `/readyz` before `POST /ingest/slack`; failed readiness is a hard stop with a message to start the bridge manually.

The bridge keeps only the current invocation in memory. It does not persist run history, replay transcripts, or maintain a queue file. Restarting the daemon clears the visible run state.

`config/codex_web_panel.yaml` is the single control point for the POC. It controls the loopback server, panel visibility, native macOS notifications, function-key toggle, Codex model/thread options, reusable AI Tools thread reset limits, Slack prompt path, and stale-source threshold. The default `codex.cwd` is `~/tmp/codex_ai_tools`, which keeps sidekick-created Codex threads out of the current project directory. On startup, the bridge exposes this repo's editable `skills/` directory as `<codex.cwd>/skills`, so Codex can read `skills/.../SKILL.md` without broad filesystem searches. The comments in that file document the current options.

Slack resolver stop conditions are surfaced as explicit run states. If no `@codex` message is found, the run becomes `not_found`. If the latest message is older than `slack.latest_message_max_age_minutes`, the run becomes `stale_source`.

`scripts/start_web_panel_daemon.sh` starts the bridge and a hidden pywebview sidekick. Use `scripts/open_web_panel.sh` to show/focus the current invocation, or use the configured `F5` Hammerspoon hotkey to toggle it. Use `scripts/start_web_panel_daemon.sh --bridge-only` only when you intentionally want HTTP ingress without the native sidekick window.

If port `8765` is occupied by an older or unrelated process, `scripts/start_web_panel_daemon.sh` prints a port diagnostic and exits. Restart on the same default port with:

```bash
./scripts/start_web_panel_daemon.sh --restart
```

Restart sends `SIGTERM` to the listener on the selected port, waits briefly, then uses `SIGKILL` only if the port is still held.

To temporarily override panel behavior for a manual daemon run:

```bash
./scripts/start_web_panel_daemon.sh --restart --panel-visibility attention
```

## Manual Testing

Run these checks from the POC worktree:

```bash
cd /Users/ashish/work/code/python/ai_tools
./scripts/start_web_panel_daemon.sh
```

Leave that terminal open. In a second terminal:

```bash
curl --fail --silent http://127.0.0.1:8765/healthz
curl --fail --silent http://127.0.0.1:8765/readyz
curl --fail --silent http://127.0.0.1:8765/api/current-run
curl --fail --silent http://127.0.0.1:8765/api/runs
```

Then reload Hammerspoon, focus Slack, post or locate an `@codex` message from Ashish, and press `ctrl+option+command+right`. Expected result: Hammerspoon shows `Queued Codex task`; the bridge receives the request; Codex.app does not open. With the default `panel.visibility: always`, the panel opens for live progress.

For visible UI testing while the daemon is running:

```bash
./scripts/open_web_panel.sh
```

Press the configured panel-toggle function key, `F5` by default, to show or hide the same native sidekick on demand. The sidekick has Rewrite and Ask modes; Ask mode supports questions even when no text is selected.

Use the `Abort` button to interrupt the current in-flight Codex turn. If Codex is waiting on an approval, Abort sends the approval `cancel` decision; otherwise it sends the app-server `turn/interrupt` request for the current `threadId` and `turnId`.

To verify the failure path, stop `scripts/start_web_panel_daemon.sh` and press the hotkey again. Expected result: Hammerspoon stops with `Codex bridge is not running` and a `Start: .../scripts/start_web_panel_daemon.sh --restart` hint; it should not open Codex.app.

Current scope: this POC supports Slack hotkey ingress, sidekick steering/continuation, explicit structured `ai_tools` text submissions through `/api/ai-tools`, and a zsh command-generation helper at `scripts/codex_nl_shell_sidekick.sh`. The AI Text Tools Hammerspoon shortcut posts minimal source context to `/api/shortcut`; the bridge resolves app policy and exposes shortcut result polling for paste-back. Hammerspoon does not spawn the Python CLI on the hot path.

## Status Messages

Status is tracked by posted and edited Slack messages, not reactions. The source thread gets one source status message after the latest non-stale `@codex` message is found.

## Files

- `slack_codex_workflow/hammerspoon/slack_codex_workflow.lua`: hotkey capture and local bridge queueing.
- `scripts/start_web_panel_daemon.sh`: manual foreground launcher for the resident local bridge.
- `scripts/run_web_panel.sh`: developer launcher for the local web panel.
- `slack_codex_workflow/scripts/launch_codex_worker.sh`: manual diagnostic path for `codex exec`; not used by the hotkey because Slack MCP writes need interactive approval.
- `slack_codex_workflow/scripts/spike_cli_auto_review.sh`: synthetic `codex exec` spike using `approvals_reviewer="auto_review"`.
- `slack_codex_workflow/prompts/codex_worker.md`: worker instructions.

## Install

Load the Hammerspoon module from `~/.hammerspoon/init.lua`:

```lua
dofile(os.getenv("HOME") .. "/work/code/python/ai_tools/slack_codex_workflow/hammerspoon/slack_codex_workflow.lua")
```
