from pathlib import Path

from ai_tools.ingress.client import (
    build_ai_tools_prompt,
    build_zsh_prompt,
    parse_submit_args,
    submit_ai_tools_invocation,
    strip_command_response,
)


def test_build_ai_tools_prompt_uses_compact_shape_specific_contract() -> None:
    prompt = build_ai_tools_prompt(
        text="pls fix this",
        app_context="Slack",
        nudge="proofread",
        render_kind="text_pair",
    )

    assert prompt.startswith("AI Tools request. Do one task on the input only. Return JSON only.")
    assert "App context: Slack" in prompt
    assert "Nudge: proofread" in prompt
    assert "pls fix this" in prompt
    assert '"render_kind"' in prompt
    assert '"structured_output"' in prompt
    assert '"corrected"' in prompt
    assert '"rewritten"' in prompt
    assert '"alternatives"' not in prompt
    assert '"text"' not in prompt
    assert "Routing rules:" not in prompt
    assert "Use the Codex model configured for this app-server session" not in prompt
    assert len(prompt) < 600


def test_build_ai_tools_prompt_single_text_schema_omits_rewrite_fields() -> None:
    prompt = build_ai_tools_prompt(
        text="explain this",
        app_context="Safari",
        nudge="explain",
        render_kind="single_text",
    )

    assert '"render_kind":"single_text"' in prompt
    assert '"text"' in prompt
    assert '"corrected"' not in prompt
    assert '"rewritten"' not in prompt
    assert '"alternatives"' not in prompt
    assert len(prompt) < 500


def test_build_ai_tools_prompt_includes_prompt_file_contents(tmp_path: Path) -> None:
    prompt_file = tmp_path / "email.md"
    prompt_file.write_text("Use concise email style.", encoding="utf-8")

    prompt = build_ai_tools_prompt(
        text="pls respond",
        app_context="Email",
        prompt_file=prompt_file,
        render_kind="text_pair",
    )

    assert "Instructions:" in prompt
    assert "Use concise email style." in prompt
    assert "pls respond" in prompt
    assert "skills/" not in prompt


def test_prompt_markdown_files_do_not_embed_output_schema() -> None:
    prompts_dir = Path(__file__).resolve().parents[1] / "prompts"

    for path in prompts_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "Output requirements" not in text
        assert "structured output" not in text.lower()
        assert "corrected:" not in text
        assert "rewritten:" not in text
        assert "alternatives:" not in text


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


def test_submit_ai_tools_invocation_posts_intent(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def read(self) -> bytes:
            return b'{"run_id": "run-1"}'

    def fake_urlopen(req, timeout=0):  # noqa: ANN001, ANN202
        captured["url"] = req.full_url
        captured["body"] = req.data
        return FakeResponse()

    monkeypatch.setattr("ai_tools.ingress.client.request.urlopen", fake_urlopen)

    submit_ai_tools_invocation(
        base_url="http://127.0.0.1:8765",
        source_kind="ai_tools",
        source_label="Ghostty",
        source_id="ai-tools-1",
        text="explain this error",
        app_context="Ghostty",
        nudge="explain",
        intent="reuse",
        show=False,
    )

    assert captured["url"] == "http://127.0.0.1:8765/api/ai-tools"
    assert b'"intent": "reuse"' in captured["body"]


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
