"""Window lifecycle helpers for the local pywebview panel."""

from __future__ import annotations

from dataclasses import dataclass
import sys
import threading
from typing import Any


def activate_macos_app() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSApplication
    except Exception:
        return False
    app = NSApplication.sharedApplication()
    try:
        app.activateIgnoringOtherApps_(True)
    except Exception:
        return False
    return True


@dataclass
class PanelWindowController:
    hidden_by_default: bool = True
    hide_delay_seconds: float = 0.05
    panel_mode: str = "rewrite"
    visible: bool = False
    window: Any | None = None

    def attach_window(self, window: Any) -> None:
        self.window = window
        self.visible = not self.hidden_by_default
        events = getattr(window, "events", None)
        closing = getattr(events, "closing", None)
        if closing is not None:
            closing += self._handle_window_closing

    def show_for_attention(self) -> dict[str, object]:
        return self.show()

    def show(self, mode: str | None = None) -> dict[str, object]:
        self.set_mode(mode)
        self.visible = True
        if self.window is not None and hasattr(self.window, "show"):
            self.window.show()
        activate_macos_app()
        return {"visible": self.visible, "panel_mode": self.panel_mode}

    def hide(self) -> dict[str, object]:
        self.visible = False
        if self.window is not None and hasattr(self.window, "hide"):
            self._schedule_hide()
        return {"visible": self.visible, "panel_mode": self.panel_mode}

    def toggle(self, mode: str | None = None) -> dict[str, object]:
        self.set_mode(mode)
        if self.visible:
            return self.hide()
        return self.show()

    def set_mode(self, mode: str | None) -> str:
        normalized = (mode or "").strip().lower()
        if normalized in {"ask", "rewrite"}:
            self.panel_mode = normalized
        return self.panel_mode

    def _handle_window_closing(self) -> bool:
        self.hide()
        return False

    def _schedule_hide(self) -> None:
        if self.hide_delay_seconds <= 0:
            self._hide_window()
            return
        timer = threading.Timer(self.hide_delay_seconds, self._hide_window)
        timer.daemon = True
        timer.start()

    def _hide_window(self) -> None:
        if self.window is not None and hasattr(self.window, "hide"):
            self.window.hide()
