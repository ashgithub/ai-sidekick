"""Entrypoint for the local Codex web panel."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

from ai_tools.codex_bridge.config import WebPanelConfig, load_web_panel_config
from ai_tools.codex_bridge.notifications import MacOSNotifier, NullNotifier, PanelAwareNotifier
from ai_tools.codex_bridge.protocol import CodexAppServerClient
from ai_tools.codex_bridge.service import CodexBridgeService
from ai_tools.codex_bridge.state import ActiveRunStateStore
from ai_tools.ingress.server import LocalIngressServer
from ai_tools.web_panel.ui_bridge import PanelUiBridge
from ai_tools.web_panel.window import PanelWindowController


PANEL_WINDOW_WIDTH = 592
PANEL_WINDOW_HEIGHT = 560
PANEL_WINDOW_MIN_WIDTH = 592
PANEL_WINDOW_MIN_HEIGHT = 500
PANEL_APP_NAME = "Codex Sidekick"
PANEL_ICON_PATH = Path(__file__).with_name("static") / "assets" / "codex-sidekick-icon.icns"


def apply_macos_app_identity(icon_path: Path = PANEL_ICON_PATH, app_name: str = PANEL_APP_NAME) -> bool:
    if sys.platform != "darwin" or not icon_path.exists():
        return False
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular, NSImage
        from Foundation import NSProcessInfo
    except Exception:
        return False

    image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
    if image is None:
        return False
    app = NSApplication.sharedApplication()
    try:
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    except Exception:
        pass
    app.setApplicationIconImage_(image)
    try:
        NSProcessInfo.processInfo().setProcessName_(app_name)
    except Exception:
        pass
    return True


def mount_repo_skills(*, repo_root: Path, codex_cwd: Path) -> Path | None:
    source = repo_root / "skills"
    target = codex_cwd / "skills"
    if not source.is_dir():
        return None
    if target.exists() or target.is_symlink():
        return target
    target.symlink_to(source, target_is_directory=True)
    return target


def apply_panel_visibility_override(config: WebPanelConfig, override: str | None) -> None:
    if not override:
        return
    allowed = {"always", "attention", "manual"}
    if override not in allowed:
        raise SystemExit(f"Invalid panel visibility: {override}. Expected one of: always, attention, manual.")
    config.panel.visibility = override


def build_service(
    cwd: Path | None = None,
    *,
    config: WebPanelConfig | None = None,
    panel_controller: PanelWindowController | None = None,
) -> CodexBridgeService:
    project_root = cwd or Path.cwd()
    config = config or load_web_panel_config(None, repo_root=project_root)
    codex_cwd = Path(config.codex.cwd).expanduser()
    if not codex_cwd.is_absolute():
        codex_cwd = project_root / codex_cwd
    codex_cwd.mkdir(parents=True, exist_ok=True)
    mount_repo_skills(repo_root=project_root, codex_cwd=codex_cwd)
    client = CodexAppServerClient(cwd=codex_cwd)
    store = ActiveRunStateStore()
    notifier: object = MacOSNotifier() if config.notifications.enabled else NullNotifier()
    if panel_controller is not None:
        notifier = PanelAwareNotifier(base=notifier, panel_controller=panel_controller)
    thread_options = {
        "approvalPolicy": config.codex.approval_policy,
        "approvalsReviewer": config.codex.approvals_reviewer,
        "personality": config.codex.personality,
        "cwd": str(codex_cwd),
    }
    if config.codex.model and config.codex.model != "inherit":
        thread_options["model"] = config.codex.model
    return CodexBridgeService(
        client=client,
        notifier=notifier,
        store=store,
        cwd=codex_cwd,
        thread_options=thread_options,
        panel_controller=panel_controller,
        reusable_thread_max_turns=config.codex.reusable_thread_max_turns,
        reusable_thread_max_age_seconds=config.codex.reusable_thread_max_age_minutes * 60,
    )


def keep_bridge_alive_after_window_exit() -> int:
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Codex web panel")
    parser.add_argument("--config", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-ui", action="store_true", help="Run the bridge and ingress without creating a webview window")
    parser.add_argument("--show-on-start", action="store_true", help="Show the panel immediately instead of starting hidden")
    args = parser.parse_args()

    repo_root = Path.cwd()
    config_path = Path(args.config) if args.config else None
    config = load_web_panel_config(config_path, repo_root=repo_root)
    apply_panel_visibility_override(config, os.environ.get("AI_TOOLS_PANEL_VISIBILITY_OVERRIDE"))
    host = args.host or config.server.host
    port = args.port or config.server.port
    panel_controller = PanelWindowController(hidden_by_default=not args.show_on_start)
    service = build_service(config=config, panel_controller=panel_controller)
    bridge = PanelUiBridge(service=service)
    static_dir = Path(__file__).with_name("static")
    server = LocalIngressServer(
        service=service,
        host=host,
        port=port,
        static_dir=static_dir,
        slack_prompt_file=config.slack.prompt_file,
        slack_latest_message_max_age_minutes=config.slack.latest_message_max_age_minutes,
        panel_visibility=config.panel.visibility,
        shortcut_profiles=config.shortcuts.profiles,
        shortcut_pending_retry_after_ms=config.shortcuts.pending_retry_after_ms,
        shortcut_review_retry_after_ms=config.shortcuts.review_retry_after_ms,
    )
    server.start()

    if args.no_ui:
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
            return 0

    import webview

    apply_macos_app_identity()
    url = f"http://{host}:{server.port}/"
    window = webview.create_window(
        PANEL_APP_NAME,
        url=url,
        js_api=bridge,
        width=PANEL_WINDOW_WIDTH,
        height=PANEL_WINDOW_HEIGHT,
        min_size=(PANEL_WINDOW_MIN_WIDTH, PANEL_WINDOW_MIN_HEIGHT),
        hidden=panel_controller.hidden_by_default,
    )
    panel_controller.attach_window(window)
    webview.start()
    return keep_bridge_alive_after_window_exit()


if __name__ == "__main__":
    raise SystemExit(main())
