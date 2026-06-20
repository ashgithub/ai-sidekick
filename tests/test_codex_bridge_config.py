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
  open_command: scripts/internal/panel-show.sh
  toggle_command: scripts/internal/panel-toggle.sh
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
shortcuts:
  pending_retry_after_ms: 250
  review_retry_after_ms: 750
  profiles:
    - name: custom-terminal
      app_patterns: ["Warp"]
      prompt_file: prompts/ask.md
      nudge: explain
      client_action: show_sidekick
    - name: default
      app_patterns: ["*"]
      client_action: poll_and_replace
""",
        encoding="utf-8",
    )

    config = load_web_panel_config(config_path, repo_root=tmp_path)

    assert config.server.port == 8876
    assert config.panel.visibility == "always"
    assert config.panel.open_command == "scripts/internal/panel-show.sh"
    assert config.panel.toggle_command == "scripts/internal/panel-toggle.sh"
    assert config.panel.open_hotkey.key == "f5"
    assert config.notifications.enabled is False
    assert config.codex.model == "gpt-5.4-mini"
    assert config.codex.reusable_thread_max_turns == 12
    assert config.codex.reusable_thread_max_age_minutes == 45
    assert config.slack.prompt_file == tmp_path / "slack_codex_workflow" / "prompts" / "codex_worker.md"
    assert config.slack.latest_message_max_age_minutes == 45
    assert config.shortcuts.pending_retry_after_ms == 250
    assert config.shortcuts.review_retry_after_ms == 750
    assert config.shortcuts.profiles[0].name == "custom-terminal"
    assert config.shortcuts.profiles[0].app_patterns == ["Warp"]
    assert config.shortcuts.profiles[0].prompt_file == tmp_path / "prompts" / "ask.md"
    assert config.shortcuts.profiles[0].nudge == "explain"
    assert config.shortcuts.profiles[0].client_action == "show_sidekick"


def test_load_web_panel_config_uses_defaults() -> None:
    config = load_web_panel_config(None, repo_root=Path("/tmp/repo"))

    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8765
    assert config.panel.visibility == "always"
    assert config.panel.open_command == "scripts/internal/panel-show.sh"
    assert config.panel.toggle_command == "scripts/internal/panel-toggle.sh"
    assert config.panel.open_hotkey.key == "f5"
    assert config.notifications.enabled is True
    assert config.codex.model == "inherit"
    assert config.codex.cwd == "~/tmp/codex_ai_tools"
    assert config.codex.reusable_thread_max_turns == 20
    assert config.codex.reusable_thread_max_age_minutes == 60
    assert config.slack.latest_message_max_age_minutes == 30
    assert config.slack.prompt_file == Path("/tmp/repo/slack_codex_workflow/prompts/codex_worker.md")
    assert [profile.name for profile in config.shortcuts.profiles] == [
        "slack",
        "email",
        "ask",
        "default",
    ]
    assert config.shortcuts.profiles[0].app_patterns == ["slack"]
    assert config.shortcuts.profiles[0].prompt_file == Path("/tmp/repo/prompts/slack.md")
    assert config.shortcuts.profiles[0].nudge == "slack"
    assert config.shortcuts.profiles[0].render_kind == "text_pair"
    assert config.shortcuts.profiles[0].client_action == "wait_for_sidekick"
    assert config.shortcuts.profiles[1].app_patterns == ["mail", "outlook"]
    assert config.shortcuts.profiles[1].prompt_file == Path("/tmp/repo/prompts/email.md")
    assert config.shortcuts.profiles[1].render_kind == "text_pair"
    assert config.shortcuts.profiles[1].client_action == "wait_for_sidekick"
    assert config.shortcuts.profiles[2].app_patterns == [
        "safari",
        "chrome",
        "terminal",
        "iterm2",
        "ghostty",
        "codex",
        "visual studio code",
        "code",
    ]
    assert config.shortcuts.profiles[2].prompt_file == Path("/tmp/repo/prompts/ask.md")
    assert config.shortcuts.profiles[2].render_kind == "single_text"
    assert config.shortcuts.profiles[2].client_action == "show_sidekick"
    assert config.shortcuts.profiles[2].show_panel is True
    assert config.shortcuts.profiles[2].panel_mode == "ask"
    assert config.shortcuts.profiles[3].prompt_file == Path("/tmp/repo/prompts/general.md")
    assert config.shortcuts.profiles[3].render_kind == "text_pair"
    assert config.shortcuts.profiles[3].client_action == "wait_for_sidekick"
    assert config.shortcuts.pending_retry_after_ms == 200
    assert config.shortcuts.review_retry_after_ms == 500
