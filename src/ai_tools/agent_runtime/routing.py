"""Nudge normalization helpers for agentic schema selection."""

from __future__ import annotations

from typing import Literal

from ai_tools.agent_runtime.types import AgentRequest

SchemaFamily = Literal["single_text", "text_pair", "alternatives", "refresh"]

EMAIL_APPS = {
    "mail",
    "outlook",
    "thunderbird",
    "gmail",
    "applemail",
}

SLACK_APPS = {
    "slack",
    "discord",
    "teams",
    "mattermost",
    "zoom",
    "skype",
    "whatsapp",
}

COMMAND_APPS = {
    "terminal",
    "iterm2",
    "ghostty",
    "alacritty",
    "hyper",
    "warp",
    "tabby",
    "kitty",
    "terminator",
}


def normalize_app_name(app_context: str | None) -> str:
    return (app_context or "").strip().lower()


def resolve_schema_family(request: AgentRequest) -> SchemaFamily:
    """Derive expected output schema family from soft nudge context."""
    action = str(request.options.get("action", "")).strip().lower()
    if action == "refresh_models":
        return "refresh"

    nudge = str(request.options.get("nudge", "")).strip().lower()
    if nudge in {"proofread", "slack", "email", "rewrite"}:
        return "text_pair"
    if nudge in {"commands", "command", "shell", "terminal"}:
        return "alternatives"
    if nudge in {"ask", "explain", "qa", "q&a"}:
        return "single_text"

    ui_tab = (request.ui_tab or "").strip().lower()
    if ui_tab in {"proofread", "rewrite"}:
        return "text_pair"
    if ui_tab in {"commands", "command"}:
        return "alternatives"
    if ui_tab in {"explain", "q&a", "qa", "ask"}:
        return "single_text"

    proofread_context = str(request.options.get("proofread_context", "")).strip().lower()
    if proofread_context in {"slack", "email", "general"}:
        return "text_pair"

    app = normalize_app_name(request.app_context)
    if app in SLACK_APPS or app in EMAIL_APPS:
        return "text_pair"
    if app in COMMAND_APPS:
        return "alternatives"

    return "single_text"
