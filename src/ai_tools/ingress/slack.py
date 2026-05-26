"""Slack-specific ingress payload normalization."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ai_tools.codex_bridge.models import SourceMetadata


class SlackIngressPayload(BaseModel):
    source_id: str
    source_label: str = Field(default="Slack")
    prompt: str

    def to_source_metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_kind="slack",
            source_label=self.source_label,
            source_id=self.source_id,
        )


def worker_prompt_path() -> Path:
    return Path(__file__).resolve().parents[3] / "slack_codex_workflow" / "prompts" / "codex_worker.md"


def build_slack_worker_prompt(
    payload_text: str,
    *,
    prompt_file: Path | None = None,
    latest_message_max_age_minutes: int = 30,
) -> str:
    worker_prompt = (prompt_file or worker_prompt_path()).read_text(encoding="utf-8").strip()
    return (
        f"{worker_prompt}\n\n"
        f"## Runtime Resolver Settings\n\n"
        f"Maximum source age: {latest_message_max_age_minutes} minutes\n\n"
        f"## Captured Hotkey Payload\n\n"
        f"{payload_text.strip()}\n"
    )
