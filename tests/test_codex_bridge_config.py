from pathlib import Path

from ai_tools.codex_bridge.config import load_web_panel_config


def test_load_web_panel_config_reads_yaml_and_resolves_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "codex_web_panel.yaml"
    config_path.write_text(
        """
server:
  host: 127.0.0.1
  port: 8876
panel:
  visibility: always
  open_command: scripts/open_web_panel.sh
  toggle_command: scripts/toggle_web_panel.sh
  open_hotkey:
    mods: []
    key: f5
notifications:
  enabled: false
codex:
  model: gpt-5.4-mini
  approval_policy: on-request
  approvals_reviewer: auto_review
  personality: pragmatic
  cwd: .
  reusable_thread_max_turns: 12
  reusable_thread_max_age_minutes: 45
slack:
  enabled: true
  prompt_file: slack_codex_workflow/prompts/codex_worker.md
  latest_message_max_age_minutes: 45
""",
        encoding="utf-8",
    )

    config = load_web_panel_config(config_path, repo_root=tmp_path)

    assert config.server.port == 8876
    assert config.panel.visibility == "always"
    assert config.panel.open_command == "scripts/open_web_panel.sh"
    assert config.panel.toggle_command == "scripts/toggle_web_panel.sh"
    assert config.panel.open_hotkey.key == "f5"
    assert config.notifications.enabled is False
    assert config.codex.model == "gpt-5.4-mini"
    assert config.codex.reusable_thread_max_turns == 12
    assert config.codex.reusable_thread_max_age_minutes == 45
    assert config.slack.prompt_file == tmp_path / "slack_codex_workflow" / "prompts" / "codex_worker.md"
    assert config.slack.latest_message_max_age_minutes == 45


def test_load_web_panel_config_uses_defaults() -> None:
    config = load_web_panel_config(None, repo_root=Path("/tmp/repo"))

    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8765
    assert config.panel.visibility == "always"
    assert config.panel.open_command == "scripts/open_web_panel.sh"
    assert config.panel.toggle_command == "scripts/toggle_web_panel.sh"
    assert config.panel.open_hotkey.key == "f5"
    assert config.notifications.enabled is True
    assert config.codex.model == "inherit"
    assert config.codex.cwd == "~/tmp/codex_ai_tools"
    assert config.codex.reusable_thread_max_turns == 20
    assert config.codex.reusable_thread_max_age_minutes == 60
    assert config.slack.latest_message_max_age_minutes == 30
    assert config.slack.prompt_file == Path("/tmp/repo/slack_codex_workflow/prompts/codex_worker.md")
