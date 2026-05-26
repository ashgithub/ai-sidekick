"""Notification backends for bridge lifecycle events."""

from __future__ import annotations

import os
import subprocess


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class NullNotifier:
    def run_started(self, title: str, message: str) -> None:
        return None

    def run_completed(self, title: str, message: str) -> None:
        return None

    def approval_needed(self, title: str, message: str) -> None:
        return None

    def run_failed(self, title: str, message: str) -> None:
        return None


class MacOSNotifier:
    def panel_url(self) -> str:
        return f"http://127.0.0.1:{os.environ.get('AI_TOOLS_WEB_PANEL_PORT', '8765')}/"

    def notify(self, title: str, message: str) -> None:
        subprocess.run(
            [
                "osascript",
                "-e",
                (
                    f'display notification "{_escape_applescript(message)}" '
                    f'with title "{_escape_applescript(title)}"'
                ),
            ],
            check=False,
        )

    def run_started(self, title: str, message: str) -> None:
        self.notify(title, f"{message} Inspect: {self.panel_url()}")

    def run_completed(self, title: str, message: str) -> None:
        self.notify(title, message)

    def approval_needed(self, title: str, message: str) -> None:
        self.notify(title, message)

    def run_failed(self, title: str, message: str) -> None:
        self.notify(title, message)


class PanelAwareNotifier:
    def __init__(self, *, base: object, panel_controller: object) -> None:
        self.base = base
        self.panel_controller = panel_controller

    def run_started(self, title: str, message: str) -> None:
        self.base.run_started(title, message)

    def run_completed(self, title: str, message: str) -> None:
        self.base.run_completed(title, message)

    def approval_needed(self, title: str, message: str) -> None:
        self.base.approval_needed(title, message)
        if hasattr(self.panel_controller, "show_for_attention"):
            self.panel_controller.show_for_attention()

    def run_failed(self, title: str, message: str) -> None:
        self.base.run_failed(title, message)
        if hasattr(self.panel_controller, "show_for_attention"):
            self.panel_controller.show_for_attention()
