import argparse
import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dev" / "agent_debug.py"
SPEC = importlib.util.spec_from_file_location("agent_debug", SCRIPT_PATH)
assert SPEC and SPEC.loader
agent_debug = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_debug)

_build_request = agent_debug._build_request
_compact_event_lines = agent_debug._compact_event_lines
_update_event_stats = agent_debug._update_event_stats


def test_build_request_uses_app_nudge_and_model():
    args = argparse.Namespace(
        app="slack",
        nudge="slack",
        model="openai.gpt-5.2",
    )

    request = _build_request(args, "hello")

    assert request.input_text == "hello"
    assert request.app_context == "slack"
    assert request.options == {"nudge": "slack"}
    assert request.selected_model == "openai.gpt-5.2"


def test_compact_event_lines_summarize_tool_and_result_signals():
    event_text = """[updates] {
  "model": {
    "messages": [{"type": "ai", "content": "done"}],
    "tool_calls": [{"name": "read_file", "args": {"file_path": "skills/ask/SKILL.md"}}],
    "structured_response": {"text": "ok"}
  }
}"""

    lines = _compact_event_lines(event_text)

    assert lines[0] == "[model] update"
    assert "  messages=1" in lines
    assert "  tool_calls=1" in lines
    assert "  structured response available" in lines


def test_update_event_stats_counts_tool_calls_and_skill_reads():
    stats = {
        "events": 0,
        "updates": 0,
        "skills_registered": 0,
        "tool_calls": 0,
        "skill_reads": 0,
        "structured_seen": False,
    }
    event_text = """[updates] {
  "model": {
    "messages": [{"type": "ai", "content": "done"}],
    "tool_calls": [{"name": "read_file", "args": {"file_path": "skills/ask/SKILL.md"}}],
    "structured_response": {"text": "ok"}
  }
}"""

    _update_event_stats(stats, event_text)

    assert stats["events"] == 1
    assert stats["updates"] == 1
    assert stats["tool_calls"] == 1
    assert stats["skill_reads"] == 1
    assert stats["structured_seen"] is True
