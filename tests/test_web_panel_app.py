from pathlib import Path

import pytest

from ai_tools.codex_bridge.config import WebPanelConfig
from ai_tools.web_panel.app import apply_panel_visibility_override, build_service
from ai_tools.web_panel.window import PanelWindowController


def test_build_service_uses_codex_config_for_thread_options(tmp_path: Path) -> None:
    config = WebPanelConfig()
    config.codex.model = "test-model"
    config.codex.cwd = "."

    service = build_service(cwd=tmp_path, config=config)

    assert service.cwd == tmp_path
    assert service.thread_options["model"] == "test-model"
    assert service.thread_options["approvalPolicy"] == "on-request"


def test_build_service_omits_model_when_config_inherits_codex_default(tmp_path: Path) -> None:
    config = WebPanelConfig()
    config.codex.model = "inherit"
    config.codex.cwd = "."

    service = build_service(cwd=tmp_path, config=config)

    assert "model" not in service.thread_options


def test_panel_visibility_override_rejects_unknown_values() -> None:
    config = WebPanelConfig()

    with pytest.raises(SystemExit, match="Invalid panel visibility"):
        apply_panel_visibility_override(config, "sometimes")


class FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def show(self) -> None:
        self.calls.append("show")

    def hide(self) -> None:
        self.calls.append("hide")


def test_panel_window_controller_can_show_hide_and_toggle() -> None:
    controller = PanelWindowController(hidden_by_default=True)
    window = FakeWindow()
    controller.attach_window(window)

    assert controller.visible is False
    assert controller.show() == {"visible": True}
    assert controller.toggle() == {"visible": False}
    assert controller.toggle() == {"visible": True}

    assert window.calls == ["show", "hide", "show"]
