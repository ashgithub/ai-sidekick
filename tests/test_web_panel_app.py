from pathlib import Path

import pytest

from ai_tools.codex_bridge.config import WebPanelConfig
from ai_tools.web_panel.app import (
    PANEL_APP_NAME,
    PANEL_ICON_PATH,
    PANEL_WINDOW_HEIGHT,
    PANEL_WINDOW_MIN_HEIGHT,
    PANEL_WINDOW_MIN_WIDTH,
    PANEL_WINDOW_WIDTH,
    apply_macos_app_identity,
    apply_panel_visibility_override,
    build_service,
    keep_bridge_alive_after_window_exit,
)
from ai_tools.web_panel.window import PanelWindowController
from ai_tools.web_panel.window import activate_macos_app


def test_build_service_uses_codex_config_for_thread_options(tmp_path: Path) -> None:
    config = WebPanelConfig()
    config.codex.model = "test-model"
    config.codex.cwd = "."
    config.codex.reusable_thread_max_turns = 7
    config.codex.reusable_thread_max_age_minutes = 15

    service = build_service(cwd=tmp_path, config=config)

    assert service.cwd == tmp_path
    assert service.thread_options["model"] == "test-model"
    assert service.thread_options["approvalPolicy"] == "on-request"
    assert service.reusable_thread_max_turns == 7
    assert service.reusable_thread_max_age_seconds == 900


def test_build_service_uses_null_notifier_when_notifications_disabled(tmp_path: Path) -> None:
    config = WebPanelConfig()
    config.codex.cwd = "."
    config.notifications.enabled = False

    service = build_service(cwd=tmp_path, config=config)

    assert service.notifier.__class__.__name__ == "NullNotifier"


def test_build_service_omits_model_when_config_inherits_codex_default(tmp_path: Path) -> None:
    config = WebPanelConfig()
    config.codex.model = "inherit"
    config.codex.cwd = "."

    service = build_service(cwd=tmp_path, config=config)

    assert "model" not in service.thread_options


def test_build_service_expands_user_codex_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config = WebPanelConfig()
    config.codex.cwd = "~/tmp/codex_ai_tools"

    service = build_service(cwd=tmp_path / "repo", config=config)

    expected = home / "tmp" / "codex_ai_tools"
    assert service.cwd == expected
    assert service.thread_options["cwd"] == str(expected)


def test_build_service_mounts_repo_skills_into_codex_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source_skills = repo / "skills"
    source_skills.mkdir(parents=True)
    (source_skills / "proofread-slack").mkdir()
    (source_skills / "proofread-slack" / "SKILL.md").write_text("slack skill", encoding="utf-8")
    codex_cwd = tmp_path / "codex-cwd"
    config = WebPanelConfig()
    config.codex.cwd = str(codex_cwd)

    build_service(cwd=repo, config=config)

    mounted = codex_cwd / "skills"
    assert mounted.is_symlink()
    assert mounted.resolve() == source_skills
    assert (mounted / "proofread-slack" / "SKILL.md").read_text(encoding="utf-8") == "slack skill"


def test_build_service_preserves_existing_codex_skills_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)
    codex_cwd = tmp_path / "codex-cwd"
    local_skills = codex_cwd / "skills"
    local_skills.mkdir(parents=True)
    (local_skills / "custom.txt").write_text("do not replace", encoding="utf-8")
    config = WebPanelConfig()
    config.codex.cwd = str(codex_cwd)

    build_service(cwd=repo, config=config)

    assert not local_skills.is_symlink()
    assert (local_skills / "custom.txt").read_text(encoding="utf-8") == "do not replace"


def test_panel_visibility_override_rejects_unknown_values() -> None:
    config = WebPanelConfig()

    with pytest.raises(SystemExit, match="Invalid panel visibility"):
        apply_panel_visibility_override(config, "sometimes")


def test_native_window_dimensions_match_sidekick_surface() -> None:
    assert PANEL_WINDOW_WIDTH == 592
    assert PANEL_WINDOW_HEIGHT == 560
    assert PANEL_WINDOW_MIN_WIDTH == 592
    assert PANEL_WINDOW_MIN_HEIGHT == 500


def test_native_window_uses_codex_sidekick_identity(tmp_path: Path) -> None:
    assert PANEL_APP_NAME == "Codex Sidekick"
    assert PANEL_ICON_PATH.name == "codex-sidekick-icon.icns"
    assert PANEL_ICON_PATH.exists()
    assert apply_macos_app_identity(icon_path=tmp_path / "missing.png") is False


def test_macos_activation_helper_is_safe_off_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_tools.web_panel.window.sys.platform", "linux")

    assert activate_macos_app() is False


class FakeEvent:
    def __init__(self) -> None:
        self.handlers: list[object] = []

    def __iadd__(self, handler: object):
        self.handlers.append(handler)
        return self


class FakeEvents:
    def __init__(self) -> None:
        self.closing = FakeEvent()


class FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.events = FakeEvents()

    def show(self) -> None:
        self.calls.append("show")

    def hide(self) -> None:
        self.calls.append("hide")


def test_panel_window_controller_can_show_hide_and_toggle() -> None:
    controller = PanelWindowController(hidden_by_default=True, hide_delay_seconds=0)
    window = FakeWindow()
    controller.attach_window(window)

    assert controller.visible is False
    assert len(window.events.closing.handlers) == 1
    assert controller.show() == {"visible": True, "panel_mode": "rewrite"}
    assert controller.toggle() == {"visible": False, "panel_mode": "rewrite"}
    assert controller.toggle(mode="ask") == {"visible": True, "panel_mode": "ask"}

    assert window.calls == ["show", "hide", "show"]


def test_panel_window_controller_intercepts_native_close_as_hide() -> None:
    controller = PanelWindowController(hidden_by_default=False, hide_delay_seconds=0)
    window = FakeWindow()
    controller.attach_window(window)

    handler = window.events.closing.handlers[0]

    assert handler() is False
    assert controller.visible is False
    assert controller.panel_mode == "rewrite"
    assert window.calls == ["hide"]


def test_keep_bridge_alive_after_window_exit_waits_until_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_sleep(seconds: int) -> None:
        nonlocal calls
        calls += seconds
        raise KeyboardInterrupt

    monkeypatch.setattr("ai_tools.web_panel.app.time.sleep", fake_sleep)

    assert keep_bridge_alive_after_window_exit() == 0
    assert calls == 1
