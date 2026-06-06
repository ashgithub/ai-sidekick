# AI Text Tools

The AI Text Tools shortcut and CLI now submit to the resident Codex sidekick by default. The legacy Tk GUI remains available as an explicit fallback.

## Workflow

1. Hammerspoon posts `{app, text, interaction}` to the resident bridge over loopback HTTP.
2. Codex runs through `codex app-server` using the model configured for that Codex session.
3. The bridge reads the profile's plain Markdown prompt file from `prompts/`.
4. The bridge resolves shortcut profiles from `config/codex_web_panel.yaml`, including app context, prompt file, review behavior, thread reuse, and client action.
5. AI Text Tools use in-memory per-tool reusable Codex threads while the daemon is alive.
6. Codex returns JSON that the sidekick renders as text, text-pair, or alternatives.

The Hammerspoon hot path avoids spawning the Python CLI. It copies selected text, posts minimal JSON to `/api/shortcut`, follows the bridge-returned client action, then pastes reviewed output back into the source app when the profile supports paste-back. Slack and email profiles wait in the sidekick after generation so you can preview the proposed text, then apply the reviewed text. Safari, Chrome, Terminal, iTerm2, Ghostty, Codex, and Code open Ask mode for explain/copy workflows. If you edit any AI-produced output in Sidekick, the primary action changes to `Review edits`; edited output must go through another AI pass before it can be applied to any source app. If no text is selected, the bridge opens the sidekick in Ask mode without submitting automatically. `scripts/run_app.sh` remains available for explicit command-line use and legacy Tk comparison, but the Hammerspoon hot path no longer falls back to it.

The `Ask Codex to revise` drawer keeps follow-up controls out of the main apply path. It defaults to the same thread and includes a `Fresh thread` option for cases where the next revision should not reuse the current Codex thread context.

Codex threads use `config/codex_web_panel.yaml -> codex.cwd`. The default is `~/tmp/codex_ai_tools`, so sidekick proofread/explain runs do not create threads under whichever project happens to be open. Reusable tool threads reset after `codex.reusable_thread_max_turns` turns or `codex.reusable_thread_max_age_minutes`, whichever comes first.

## Covered Shortcut Profiles

- Slack uses `prompts/slack.md`, opens Rewrite mode, and waits for review/apply.
- Mail and Outlook use `prompts/email.md`, open Rewrite mode, and wait for review/apply.
- Safari, Chrome, Terminal, iTerm2, Ghostty, Codex, and Code use `prompts/ask.md`, open Ask mode, and are intended for explain/copy.
- The default profile uses `prompts/general.md`, opens Rewrite mode, and waits for review/apply.

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

These commands post explicit structured text-tool work to `http://127.0.0.1:8765/api/ai-tools` and show the sidekick. Add `--intent reuse` to use the same per-tool reuse behavior as Hammerspoon. Start the sidekick first:

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
- Hammerspoon `ctrl+option+command+\` waits for sidekick review before paste-back for rewrite profiles, and opens Ask mode for explain/copy profiles.
- Sidekick edited output changes the primary action to `Review edits` and cannot be applied to source until the reviewed follow-up output completes.
- Ghostty, Terminal, iTerm2, Codex, Code, Safari, and Chrome route to the explain prompt for the Hammerspoon text shortcut.
- Command suggestions render alternatives in the sidekick, and each alternative can be selected/copied from the current invocation.
- Explain/ask requests remain visible in the sidekick as single-text answers.

The hard part is preserving the old synchronous edit contract: capture selected text, submit it to Codex, choose the right output, paste it back into the original app, and restore the clipboard without surprising the user.

## Window Placement

When `--window-x` and `--window-y` are missing, the app starts centered in the visible desktop bounds.
