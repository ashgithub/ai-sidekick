# Slack Codex Workflow

Hotkey-driven Slack-to-Codex workflow for turning Slack messages into Codex work items.

## Contract

- Use Slack app only.
- Every Slack message from the worker starts with `[from codex :bot:]`.
- The wand status message stays in the source thread.
- No reactions are used.
- The latest recent `@codex` message from Ashish is the queue.
- `#codex-work` is not used.
- No local queue is used.
- Task state is tracked in the source Slack thread with a source status message for visible milestone updates.

## Hotkey

`ctrl+option+command+right`

The hotkey captures local Slack window context, opens the pinned Codex.app workspace, creates a new chat, and submits the worker prompt there so Slack MCP writes can be approved interactively. It does not copy selected Slack text or read existing clipboard content. Hammerspoon shows a generic `Looking for recent @codex task` notification; Codex confirms the actual source after Slack search.

## Flow

1. Post a Slack message that starts with or contains `@codex`.
2. Press `ctrl+option+command+right` within five minutes.
3. Hammerspoon captures app/window/context details only.
4. Hammerspoon copies the full worker prompt to the clipboard.
5. Hammerspoon opens Codex.app on this workflow workspace and submits the prompt in a new chat.
6. Codex verifies Slack MCP is available.
7. Codex searches for Ashish's newest `@codex` message from the last five minutes.
8. If no recent match is found, Codex stops with the not-found message.
9. If a match is found, Codex reads that source thread.
10. Codex posts a source status thread reply that starts with `[from codex :bot:] :magic_wand: Found recent @codex task`.
11. Codex edits that same source status message for important milestones.
12. Codex completes the work, replies in the original Slack conversation when appropriate, and updates the source status message to completed or failed.

## Source Resolver Cache

`slack_codex_workflow/config/source_resolver_cache.json` is a legacy source resolver cache for frequently used Slack channels and DMs. It maps exact Slack window titles or aliases to known Slack channel or user IDs.

It is not a queue, spool, inbox, or task-state file. The worker does not use it to choose the source task and does not update it during this workflow.

## Status Messages

Status is tracked by posted and edited Slack messages, not reactions. The source thread gets one source status message after the recent `@codex` message is found.

## Files

- `slack_codex_workflow/hammerspoon/slack_codex_workflow.lua`: hotkey capture and Codex.app handoff.
- `slack_codex_workflow/config/source_resolver_cache.json`: optional exact-match Slack source resolver cache.
- `slack_codex_workflow/scripts/launch_codex_worker.sh`: manual diagnostic path for `codex exec`; not used by the hotkey because Slack MCP writes need interactive approval.
- `slack_codex_workflow/scripts/spike_cli_auto_review.sh`: synthetic `codex exec` spike using `approvals_reviewer="auto_review"`.
- `slack_codex_workflow/scripts/spike_open_codex_app.sh`: synthetic Codex.app handoff test.
- `slack_codex_workflow/prompts/codex_worker.md`: worker instructions.

## Install

Load the Hammerspoon module from `~/.hammerspoon/init.lua`:

```lua
dofile(os.getenv("HOME") .. "/work/code/python/ai_tools/slack_codex_workflow/hammerspoon/slack_codex_workflow.lua")
```
