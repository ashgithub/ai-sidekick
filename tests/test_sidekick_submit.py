from pathlib import Path

from ai_tools.ingress.client import (
    build_ai_tools_prompt,
    build_zsh_prompt,
    parse_submit_args,
    strip_command_response,
)


def test_build_ai_tools_prompt_includes_context_and_text() -> None:
    prompt = build_ai_tools_prompt(
        text="pls fix this",
        app_context="Slack",
        nudge="proofread",
    )

    assert "AI Tools request" in prompt
    assert "App context: Slack" in prompt
    assert "Nudge: proofread" in prompt
    assert "pls fix this" in prompt


def test_parse_submit_args_defaults_to_sidekick_source() -> None:
    args = parse_submit_args(["--text", "hello", "--intent", "continue"])

    assert args.text == "hello"
    assert args.intent == "continue"
    assert args.source_kind == "ai_tools"
    assert args.source_label == "AI Tools"


def test_build_zsh_prompt_requests_one_safe_command() -> None:
    prompt = build_zsh_prompt("find large files")

    assert "one safe zsh command" in prompt
    assert "Return only the command" in prompt
    assert "find large files" in prompt


def test_strip_command_response_removes_markdown_fence() -> None:
    assert strip_command_response("```bash\nls -la\n```") == "ls -la"


def test_zsh_docs_and_demo_use_sidekick_helper() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    paths = [
        repo_root / "docs" / "codex-nl-shell-shortcut.md",
        repo_root / "docs" / "presentations" / "codex-nl-shell.md",
        repo_root / "scripts" / "demo_codex_nl_shell_shortcut.sh",
    ]

    for path in paths:
        text = path.read_text()
        assert "scripts/codex_nl_shell_sidekick.sh" in text
        assert "codex exec" not in text
        assert "CODEX_NL_MODEL" not in text
