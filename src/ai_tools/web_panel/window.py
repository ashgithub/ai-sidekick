"""Window lifecycle helpers for the local pywebview panel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PanelWindowController:
    hidden_by_default: bool = True
    visible: bool = False
    window: Any | None = None

    def attach_window(self, window: Any) -> None:
        self.window = window
        self.visible = not self.hidden_by_default

    def show_for_attention(self) -> dict[str, bool]:
        return self.show()

    def show(self) -> dict[str, bool]:
        self.visible = True
        if self.window is not None and hasattr(self.window, "show"):
            self.window.show()
        return {"visible": self.visible}

    def hide(self) -> dict[str, bool]:
        self.visible = False
        if self.window is not None and hasattr(self.window, "hide"):
            self.window.hide()
        return {"visible": self.visible}

    def toggle(self) -> dict[str, bool]:
        if self.visible:
            return self.hide()
        return self.show()
