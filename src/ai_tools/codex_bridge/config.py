"""Configuration for the local Codex companion bridge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765


class HotkeyConfig(BaseModel):
    mods: list[str] = Field(default_factory=list)
    key: str = "f5"


class PanelConfig(BaseModel):
    visibility: Literal["always", "attention", "manual"] = "always"
    open_command: str = "scripts/open_web_panel.sh"
    open_hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)


class CodexConfig(BaseModel):
    model: str = "gpt-5.4-mini"
    approval_policy: str = "on-request"
    approvals_reviewer: str = "auto_review"
    personality: str = "pragmatic"
    cwd: str = "."


class SlackConfig(BaseModel):
    enabled: bool = True
    prompt_file: Path = Path("slack_codex_workflow/prompts/codex_worker.md")
    status_mode: str = "source_message"
    latest_message_max_age_minutes: int = 30


class WebPanelConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    panel: PanelConfig = Field(default_factory=PanelConfig)
    codex: CodexConfig = Field(default_factory=CodexConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)


def default_config_path(repo_root: Path) -> Path:
    return repo_root / "config" / "codex_web_panel.yaml"


def _resolve_repo_path(value: Path, *, repo_root: Path) -> Path:
    return value if value.is_absolute() else repo_root / value


def load_web_panel_config(config_path: Path | None, *, repo_root: Path) -> WebPanelConfig:
    path = config_path or default_config_path(repo_root)
    payload: dict[str, Any] = {}
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = WebPanelConfig.model_validate(payload)
    config.slack.prompt_file = _resolve_repo_path(config.slack.prompt_file, repo_root=repo_root)
    return config


def config_for_lua(config: WebPanelConfig) -> dict[str, Any]:
    return {
        "server": config.server.model_dump(mode="json"),
        "panel": config.panel.model_dump(mode="json"),
        "slack": {
            "enabled": config.slack.enabled,
            "prompt_file": str(config.slack.prompt_file),
            "status_mode": config.slack.status_mode,
            "latest_message_max_age_minutes": config.slack.latest_message_max_age_minutes,
        },
    }


def config_for_lua_json(config: WebPanelConfig) -> str:
    return json.dumps(config_for_lua(config), sort_keys=True)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Print Codex web panel config")
    parser.add_argument("--config", default=None)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--lua-json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    config_path = Path(args.config) if args.config else None
    config = load_web_panel_config(config_path, repo_root=repo_root)
    if args.lua_json:
        print(config_for_lua_json(config))
    else:
        print(config.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
