from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hammerspoon_ai_tools_shortcut_posts_to_sidekick_before_tk_fallback() -> None:
    lua = (ROOT / "init.lua").read_text(encoding="utf-8")

    assert "local ai_tools_sidekick_enabled = true" in lua
    assert "/api/ai-tools" in lua
    assert "/api/panel/show" in lua
    assert "/api/panel/toggle" in (ROOT / "scripts" / "toggle_web_panel.sh").read_text(encoding="utf-8")
    assert "--source-kind ai_tools" in lua
    assert "--app %q" in lua
    assert "<<'EOF'" in lua
    assert "scripts/run_app.sh" in lua
    assert "--wait --no-show" in lua
    assert "submit_ai_tools_direct" in lua
    assert "poll_ai_tools_result" in lua
    assert "wait_for_ai_tools_user_selection" in lua
    assert "should_wait_for_sidekick_selection" in lua
    assert "open_ai_tools_ask_mode" in lua
    assert '["mode"] = "ask"' in lua
    assert "Ask in the sidekick" in lua
    assert "hs.json.encode" in lua
    assert "hs.http.asyncPost(urls.ai_tools" in lua
    assert '"intent"] = "reuse"' in lua
    assert "hs.pasteboard.setContents(stdOut)" in lua
    assert "Queued in Codex sidekick" in lua
    assert '["Ghostty"] = terminal_config' in lua
    assert 'lowered:match("ghostty")' in lua
    assert 'app_bucket == "iterm2" or app_bucket == "ghostty"' in lua
    assert 'app_bucket == "slack"' in lua
    assert '--nudge explain' in lua
    assert "/private/tmp/ai_tools-shortcut-web-panel-poc" not in lua
    assert "clients/multi_tool_client.py" in lua
