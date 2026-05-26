# AI Text Tools

The AI Text Tools app is a universal Tk GUI and CLI wrapper around the local Deep Agent runtime.

## Workflow

1. One input workspace is shown in the UI.
2. Deep Agent receives all skills from `skills/*/SKILL.md`.
3. `skills/AGENTS.md` is loaded as global memory.
4. A soft nudge from `--nudge` or app context selects the expected output schema.
5. The agent decides which skill or tool to use.
6. Deep Agents backend uses `FilesystemBackend(root_dir=<project>)`.
7. Runtime injects the configured nudge prompt from `config.yaml -> agentic_routing.nudge_prompts`.

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

Legacy flags remain accepted for compatibility:

```bash
./scripts/run_app.sh --tab Proofread --app slack --text "quick draft message"
```

## Refresh Models

Use the `Refresh Models` button in the GUI.

Refresh runs through `skills/refresh-llms/scripts/refresh_llms.sh` via runtime action `refresh_models`.

## Window Placement

When `--window-x` and `--window-y` are missing, the app starts centered in the visible desktop bounds.
