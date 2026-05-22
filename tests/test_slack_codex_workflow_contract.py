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


def test_worker_requires_slack_app_only_and_forbids_reactions() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")

    assert "Use Slack app only" in prompt
    assert "tool_search" in prompt
    assert "Slack connector unavailable. Cannot process Codex Slack workflow." in prompt
    assert "Do not use reactions" in prompt
    assert "#codex-work" not in prompt


def test_worker_uses_recent_codex_mentions_from_ashish_as_task_source() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")

    assert "Recent @codex Search" in prompt
    assert "from:<@W6B8KA2E8>" in prompt
    assert "five minutes" in prompt
    assert "after" in prompt
    assert "sort by timestamp descending" in prompt
    assert "No recent `@codex` message from Ashish found in the last 5 minutes." in prompt
    assert "If multiple matches are returned, use the newest result" in prompt


def test_worker_can_safely_handle_empty_captured_text() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")
    lua = read_workflow_file("hammerspoon", "slack_codex_workflow.lua")

    assert "Captured text selection: " in lua
    assert 'selection_state = "empty"' in lua
    assert "Do not resolve work from Slack window title alone" in prompt
    assert "recent `@codex` search" in prompt
    assert "Do not guess" in prompt
    assert "post `@codex ...` again" in prompt


def test_hotkey_does_not_copy_or_use_selected_slack_text() -> None:
    lua = read_workflow_file("hammerspoon", "slack_codex_workflow.lua")
    docs = read_doc_file("slack-codex-workflow.md")

    assert 'hs.eventtap.keyStroke({ "cmd" }, "c")' not in lua
    assert "capture_clipboard_text" not in lua
    assert "Captured text capture mode: none" in lua
    assert 'local copied_text = ""' in lua
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
    assert "[from codex :bot:]" in lua


def test_worker_forbids_reaction_api_usage() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")

    assert "Status Reactions" not in prompt
    assert "Do not use reactions" in prompt
    assert "source status message" in prompt


def test_source_resolver_cache_is_durable_config_not_task_state() -> None:
    prompt = read_workflow_file("prompts", "codex_worker.md")
    docs = read_doc_file("slack-codex-workflow.md")
    cache = json.loads(read_workflow_file("config", "source_resolver_cache.json"))

    assert "Source Resolver Cache" in prompt
    assert "config/source_resolver_cache.json" in prompt
    assert "legacy resolver config" in prompt
    assert "Do not update the cache" in prompt
    assert "not a queue, spool, inbox, or task-state file" in prompt
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


def test_hammerspoon_hotkey_uses_codex_app_handoff_not_exec_launcher() -> None:
    lua = read_workflow_file("hammerspoon", "slack_codex_workflow.lua")

    assert 'local hotkey_mods = { "ctrl", "alt", "cmd" }' in lua
    assert 'local hotkey_key = "right"' in lua
    assert "scripts/launch_codex_worker.sh" not in lua
    assert '"/opt/homebrew/bin/codex"' in lua
    assert '"app"' in lua
    assert "submit_codex_app_prompt_from_clipboard" in lua
    assert "hs.pasteboard.setContents(full_prompt)" in lua
    assert "Use Slack app only" in lua
    assert "Looking for recent @codex task" in lua
    assert "#codex-work" not in lua


def test_readme_states_the_non_negotiable_contract() -> None:
    docs = read_doc_file("slack-codex-workflow.md")

    assert "Use Slack app only." in docs
    assert "Every Slack message from the worker starts with `[from codex :bot:]`." in docs
    assert "No reactions are used." in docs
    assert "No local queue is used." in docs
    assert "The latest recent `@codex` message from Ashish is the queue." in docs
    assert "`#codex-work` is not used." in docs
