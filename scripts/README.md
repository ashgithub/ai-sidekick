# Scripts

This folder contains implementation helpers for Sidekick. Human-facing commands live in `../bin`.

## Human-Facing Commands

Run these from the repo root.

| Command | Use |
| --- | --- |
| `./bin/sidekick` | Start the resident Sidekick bridge and native panel. |
| `./bin/sidekick --restart` | Restart the bridge on the configured port. |
| `./bin/codex-nl-shell` | zsh/Ghostty natural-language-to-shell helper. Usually called by the zsh widget, not manually. |
| `./bin/sidekick-check` | Run lint, compile, and tests before check-in. |

## Internal App-Facing Helpers

These are called by Hammerspoon, config, or other scripts. Do not treat them as normal user commands.

| Script | Use |
| --- | --- |
| `scripts/internal/env.sh` | Shared Python/uv environment selection. |
| `scripts/internal/config-json.sh` | Render web-panel YAML config as JSON for Hammerspoon. |
| `scripts/internal/panel-show.sh` | Ask the running bridge to show/focus the native panel. |
| `scripts/internal/panel-toggle.sh` | Ask the running bridge to toggle the native panel. |

## Developer Utilities

These are for diagnostics or maintenance.

| Script | Use |
| --- | --- |
| `scripts/dev/web-panel-dev.sh` | Launch the panel visibly for UI development. |
| `scripts/dev/sidekick-submit-text.sh` | Manually submit text to `/api/ai-tools`. |
| `scripts/dev/agent_debug.py` | Run the deep-agent runtime without the UI. |
| `scripts/dev/oci_list_models.py` | Diagnose OCI model catalog access. |
| `scripts/dev/icon-build.sh` | Build the macOS `.icns` asset. |
| `scripts/dev/icon_mask.py` | Apply the rounded macOS icon mask to the PNG asset. |

## Demo

| Script | Use |
| --- | --- |
| `scripts/demo/codex-nl-shell-demo.sh` | Demonstrate the zsh command helper without executing the generated command. |

## Compatibility Wrappers

The old flat script names remain as small wrappers so external config does not break immediately:

| Wrapper | Forwards to |
| --- | --- |
| `scripts/start_web_panel_daemon.sh` | `bin/sidekick` |
| `scripts/codex_nl_shell_sidekick.sh` | `bin/codex-nl-shell` |
| `scripts/test_app.sh` | `bin/sidekick-check` |
| `scripts/open_web_panel.sh` | `scripts/internal/panel-show.sh` |
| `scripts/toggle_web_panel.sh` | `scripts/internal/panel-toggle.sh` |
| `scripts/codex_web_panel_config_json.sh` | `scripts/internal/config-json.sh` |
| `scripts/common_env.sh` | `scripts/internal/env.sh` |
| `scripts/run_web_panel.sh` | `scripts/dev/web-panel-dev.sh` |
| `scripts/run_app.sh` | `scripts/dev/sidekick-submit-text.sh`; `--tk` now exits with an error. |

The legacy Tk client has been removed. Sidekick is the only supported UI path.
