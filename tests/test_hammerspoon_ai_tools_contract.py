from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hammerspoon_ai_tools_shortcut_posts_minimal_payload_to_shortcut_endpoint() -> None:
    lua = (ROOT / "init.lua").read_text(encoding="utf-8")

    assert "local ai_tools_sidekick_enabled = true" in lua
    assert "/api/shortcut" in lua
    assert "/api/shortcut/results/" in lua
    assert "/api/panel/toggle" in (ROOT / "scripts" / "toggle_web_panel.sh").read_text(encoding="utf-8")
    assert "hs.json.encode" in lua
    assert "hs.http.asyncPost(urls.shortcut" in lua
    assert '["app"] = appName' in lua
    assert '["text"] = text' in lua
    assert '["interaction"] = "replace-selection"' in lua
    assert "Queued in Codex sidekick" in lua
    assert '["Ghostty"] = terminal_config' in lua
    assert "submit_ai_tools_direct" not in lua
    assert "should_wait_for_sidekick_selection" not in lua
    assert "wait_for_ai_tools_user_selection" not in lua
    assert "run_ai_tools_cli_fallback" not in lua
    assert "terminal_statuses" not in lua
    assert '"intent"] = "reuse"' not in lua
    assert '"nudge"] = nudge' not in lua
    assert "--source-kind ai_tools" not in lua
    assert "--wait --no-show" not in lua
    assert "--nudge explain" not in lua
    assert "<<'EOF'" not in lua
    assert "/private/tmp/ai_tools-shortcut-web-panel-poc" not in lua
    assert "clients/multi_tool_client.py" not in lua


def test_hammerspoon_shortcut_polling_ignores_stale_callbacks_and_closed_server() -> None:
    lua = (ROOT / "init.lua").read_text(encoding="utf-8")

    assert "local active_shortcut_token = 0" in lua
    assert "local function next_shortcut_token()" in lua
    assert "local function is_active_shortcut(shortcut_token)" in lua
    assert "local function is_connection_failure(status)" in lua
    assert "if not is_active_shortcut(shortcut_token) then" in lua
    assert "restore_clipboard_later(originalClipboard, shortcut_token)" in lua
    assert "restore_clipboard_now(originalClipboard, shortcut_token)" in lua
    assert "poll_shortcut_result(result_url, trigger_app, appName, config, originalClipboard, shortcut_token)" in lua
    assert "local function run_processing(trigger_app, appName, config, shortcut_token)" in lua
    assert "function processAppText()" in lua
    assert "local shortcut_token = next_shortcut_token()\n\n    hs.timer.doAfter" in lua
    assert "run_processing(trigger_app, appName, config, shortcut_token)" in lua
    assert "log.i(\"Sidekick result polling stopped" in lua
    assert "log.e(\"Sidekick result polling stopped" not in lua
    assert 'show_status("error", appName, "Sidekick result check failed.", true)' not in lua


def test_hammerspoon_exposes_apply_callback_for_sidekick_only_runs() -> None:
    lua = (ROOT / "init.lua").read_text(encoding="utf-8")

    assert 'hs.urlevent.bind("apply_ai_tools_output"' in lua
    assert 'window.location.href = `hammerspoon://apply_ai_tools_output?' not in lua
    assert 'target_app = hs.application.find(appName)' in lua
    assert 'config.paste()' in lua
