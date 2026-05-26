from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hammerspoon_ai_tools_shortcut_posts_to_sidekick_before_tk_fallback() -> None:
    lua = (ROOT / "init.lua").read_text(encoding="utf-8")

    assert "local ai_tools_sidekick_enabled = true" in lua
    assert "/api/invoke" in lua
    assert "/api/panel/show" in lua
    assert 'source_kind = "ai_tools"' in lua
    assert "Queued in Codex sidekick" in lua
    assert "/private/tmp/ai_tools-shortcut-web-panel-poc" not in lua
    assert "clients/multi_tool_client.py" in lua
