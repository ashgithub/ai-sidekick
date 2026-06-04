# AI Text Tools

The AI Text Tools shortcut and CLI now submit to the resident Codex sidekick by default. The legacy Tk GUI remains available as an explicit fallback.

## Workflow

1. Hammerspoon posts shortcut text directly to the resident bridge over loopback HTTP.
2. Codex runs through `codex app-server` using the model configured for that Codex session.
3. The prompt points Codex at the relevant `skills/*/SKILL.md` instructions.
4. A soft nudge from `--nudge` or app context selects the expected output shape.
5. AI Text Tools use in-memory per-tool reusable Codex threads while the daemon is alive.
6. Codex returns JSON that the sidekick renders as text, text-pair, or alternatives.

The Hammerspoon hot path avoids spawning the Python CLI. It copies selected text, posts JSON to `/api/ai-tools`, polls the accepted run, then pastes the primary output back into the source app. Slack is the exception: Slack text runs wait in the sidekick after generation so you can preview and edit the proposed text, then `Use selected version` pastes/submits the reviewed text. If no text is selected, the shortcut opens the sidekick in Ask mode without submitting automatically. `scripts/run_app.sh` remains available for command-line use and as a fallback.

Codex threads use `config/codex_web_panel.yaml -> codex.cwd`. The default is `~/tmp/codex_ai_tools`, so sidekick proofread/explain runs do not create threads under whichever project happens to be open. The bridge mounts this repo's editable `skills/` directory into that cwd as `<codex.cwd>/skills`, so prompts can use local skill paths without broad filesystem searches. Reusable tool threads reset after `codex.reusable_thread_max_turns` turns or `codex.reusable_thread_max_age_minutes`, whichever comes first.

## Output Schemas

- `SingleText`: returns `text`.
- `TextPair`: returns `corrected` and `rewritten`.
- `Alternatives`: returns `alternatives[]`, where each item has `value` and `explanation`.

## Run From Command Line

```bash
./scripts/run_app.sh --text "Explain CAP theorem"
./scripts/run_app.sh --nudge slack --app slack --text "hi team pls review by tomrw"
./scripts/run_app.sh --nudge commands --text "list large files in current directory"
```

These commands post structured text-tool work to `http://127.0.0.1:8765/api/ai-tools` and show the sidekick. Add `--intent reuse` to use the same per-tool reuse behavior as Hammerspoon. Start the sidekick first:

```bash
./scripts/start_web_panel_daemon.sh --restart
```

Use the legacy Tk GUI explicitly if you need to compare behavior while validating the sidekick:

```bash
./scripts/run_app.sh --tk --tab Proofread --app slack --text "quick draft message"
```

Legacy flags such as `--tab`, `--app`, `--nudge`, and `--text` remain accepted for sidekick submission.

## Tk Removal Gates

Do not remove the legacy Tk client until these sidekick behaviors are manually approved:

- Proofread/rewrite returns structured `Corrected` and `Rewritten` outputs, with `Rewritten` as the default paste-back result.
- Slack context uses Slack-friendly formatting and emoji behavior; non-Slack contexts do not force emoji.
- Hammerspoon `ctrl+option+command+\` replaces selected text with the primary output after the sidekick run completes, except Slack where the sidekick waits for explicit `Use selected version`.
- Terminal app contexts including iTerm2 and Ghostty route to the explain skill for the Hammerspoon text shortcut.
- Command suggestions render alternatives in the sidekick, and each alternative can be selected/copied from the current invocation.
- Explain/ask requests remain visible in the sidekick as single-text answers.

The hard part is preserving the old synchronous edit contract: capture selected text, submit it to Codex, choose the right output, paste it back into the original app, and restore the clipboard without surprising the user.

## Window Placement

When `--window-x` and `--window-y` are missing, the app starts centered in the visible desktop bounds.
