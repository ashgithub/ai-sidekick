from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "slack_codex_workflow"


def read_workflow_file(*parts: str) -> str:
    return (WORKFLOW / Path(*parts)).read_text(encoding="utf-8")


def read_doc_file(*parts: str) -> str:
    return (ROOT / "docs" / Path(*parts)).read_text(encoding="utf-8")


def test_launcher_runs_worker_without_local_queue_state() -> None:
    launcher = read_workflow_file("scripts", "launch_codex_worker.sh")

    assert '"${CODEX_BIN}" exec' in launcher
    assert "--ephemeral" in launcher
    assert "mktemp" not in launcher
    assert "queue_dir" not in launcher.lower()
    assert "spool" not in launcher.lower()


def test_worker_uses_slack_for_source_resolution_and_forbids_reactions() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")

    assert "Use Slack to resolve the source task and post replies/status updates." in prompt
    assert "Use other connectors when the requested work requires them." in prompt
    assert "tool_search" in prompt
    assert "Slack connector unavailable. Cannot process Codex Slack workflow." in prompt
    assert "Do not use reactions" in prompt
    assert "#codex-work" not in prompt


def test_worker_uses_recent_codex_mentions_from_ashish_as_task_source() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")

    assert "Latest @codex Search" in prompt
    assert "from:<@W6B8KA2E8>" in prompt
    assert "Do not pass an `after` timestamp" in prompt
    assert "sort=\"timestamp\"" in prompt
    assert "sort_dir=\"desc\"" in prompt
    assert "limit=1" in prompt
    assert "include_context=false" in prompt
    assert "No `@codex` message from Ashish found." in prompt
    assert "Stale @codex message found" in prompt
    assert "Maximum source age:" in prompt


def test_hotkey_payload_only_contains_resolver_metadata() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")
    lua = read_workflow_file("hammerspoon", "slack_codex_workflow.lua")

    assert "Request time:" in lua
    assert "Task resolver: latest @codex message from Ashish" in lua
    assert "Window title:" not in lua
    assert "Bundle id:" not in lua
    assert "Captured text:" not in lua
    assert "Captured text selection:" not in lua
    assert "latest `@codex` search" in prompt
    assert "Do not guess" in prompt
    assert "post `@codex ...` again" in prompt


def test_hotkey_does_not_copy_or_use_selected_slack_text() -> None:
    lua = read_workflow_file("hammerspoon", "slack_codex_workflow.lua")
    docs = read_doc_file("slack-codex-workflow.md")

    assert 'hs.eventtap.keyStroke({ "cmd" }, "c")' not in lua
    assert "capture_clipboard_text" not in lua
    assert "Captured text capture mode" not in lua
    assert "copied_text" not in lua
    assert "does not copy selected Slack text" in docs


def test_worker_posts_and_updates_source_status_message() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")
    docs = read_doc_file("slack-codex-workflow.md")

    assert "Source Status Message" in prompt
    assert "[from codex :bot:] :magic_wand: Found recent @codex task" in prompt
    assert "send a source status message as a thread reply" in prompt
    assert "edit the same source status message" in prompt
    assert "important milestones" in prompt
    assert "source status message" in docs


def test_worker_prefixes_all_slack_messages_from_codex() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")
    lua = read_workflow_file("hammerspoon", "slack_codex_workflow.lua")

    assert "[from codex :bot:]" in prompt
    assert "Every Slack message you send or edit must start with `[from codex :bot:]`" in prompt
    assert "Task resolver: latest @codex message from Ashish" in lua


def test_worker_forbids_reaction_api_usage() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")

    assert "Status Reactions" not in prompt
    assert "Do not use reactions" in prompt
    assert "source status message" in prompt


def test_source_resolver_cache_is_durable_config_not_task_state() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")
    docs = read_doc_file("slack-codex-workflow.md")
    cache = json.loads(read_workflow_file("config", "source_resolver_cache.json"))

    assert "source_resolver_cache.json" not in prompt
    assert "window title" not in prompt.lower()
    assert "source resolver cache" in docs
    assert cache["version"] == 1
    assert "window_title_aliases" in cache
    assert "channel_aliases" in cache
    assert "user_aliases" in cache
    assert "schema" in cache


def test_cli_auto_review_spike_uses_exec_with_auto_review() -> None:
    script = read_workflow_file("scripts", "spike_cli_auto_review.sh")

    assert '"${CODEX_BIN}" exec' in script
    assert "approval_policy=\"on-request\"" in script
    assert "approvals_reviewer=\"auto_review\"" in script
    assert "--ephemeral" in script
    assert "SLACK_CODEX_CLI_AUTO_REVIEW_SPIKE_" in script
    assert "#codex-work" not in script


def test_hammerspoon_hotkey_requires_manually_started_bridge() -> None:
    lua = read_workflow_file("hammerspoon", "slack_codex_workflow.lua")

    assert 'local hotkey_mods = { "ctrl", "alt", "cmd" }' in lua
    assert 'local hotkey_key = "right"' in lua
    assert "/readyz" in lua
    assert "hs.http.asyncGet" in lua
    assert "/ingest/slack" in lua
    assert "Queued Codex task" in lua
    assert "panel_visibility" in lua
    assert "open_panel" in lua
    assert "panel_open_hotkey_mods" in lua
    assert "panel_open_hotkey_key" in lua
    assert "hs.hotkey.bind(panel_open_hotkey_mods" in lua
    assert "scripts/start_web_panel_daemon.sh" in lua
    assert "Start the Codex bridge first" in lua
    assert "scripts/ensure_web_panel.sh" not in lua
    assert "Local bridge unavailable; opening Codex Slack worker" not in lua
    assert "launch_codex_app_fallback" not in lua
    assert "Codex.app" not in lua
    assert "hs.application.launchOrFocus" not in lua
    assert "hs.pasteboard.setContents" not in lua
    assert "Task resolver: latest @codex message from Ashish" in lua
    assert "Looking for latest @codex task" in lua
    assert "#codex-work" not in lua


def test_manual_bridge_launcher_uses_yaml_config_and_open_panel_helper() -> None:
    common_env = (ROOT / "scripts" / "common_env.sh").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts" / "start_web_panel_daemon.sh").read_text(encoding="utf-8")
    opener = (ROOT / "scripts" / "open_web_panel.sh").read_text(encoding="utf-8")
    config_helper = (ROOT / "scripts" / "codex_web_panel_config_json.sh").read_text(encoding="utf-8")

    assert "AI_TOOLS_WEB_PANEL_STATE_PATH" not in common_env
    assert "--config" in launcher
    assert "--panel-visibility" in launcher
    assert "/readyz" in launcher
    assert "Panel URL:" in launcher
    assert "Open panel:" in launcher
    assert "already has a compatible bridge running" in launcher
    assert "is already in use by another process" in launcher
    assert "--restart" in launcher
    assert "Restarting listener on port" in launcher
    assert "kill \"${pid}\"" in launcher
    assert "kill -KILL \"${pid}\"" in launcher
    assert "Could not stop PID" in launcher
    assert "Leave this terminal open" in launcher
    assert "/usr/bin/open" in opener
    assert "http://127.0.0.1:${PORT}/" in opener
    assert "ai_tools.codex_bridge.config" in config_helper


def test_readme_states_the_non_negotiable_contract() -> None:
    docs = read_doc_file("slack-codex-workflow.md")

    assert "Use Slack to resolve the source task and post replies/status updates." in docs
    assert "Every Slack message from the worker starts with `[from codex :bot:]`." in docs
    assert "No reactions are used." in docs
    assert "No local queue is used." in docs
    assert "The latest `@codex` message from Ashish is the queue." in docs
    assert "`#codex-work` is not used." in docs
