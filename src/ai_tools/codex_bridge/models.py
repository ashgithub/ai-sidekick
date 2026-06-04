"""Typed models for the resident Codex bridge."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunStatus(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    APPROVAL_NEEDED = "approval_needed"
    NOT_FOUND = "not_found"
    STALE_SOURCE = "stale_source"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SourceMetadata(BaseModel):
    source_kind: str
    source_label: str
    source_id: str


class TranscriptEntry(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    kind: str
    message: str
    payload: dict[str, Any] | None = None


class TraceEntry(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    kind: str
    label: str
    tool_name: str | None = None
    status: str | None = None
    duration_ms: int | None = None
    error: str | None = None


class RunRecord(BaseModel):
    run_id: str
    source: SourceMetadata
    prompt: str
    status: RunStatus = RunStatus.QUEUED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    thread_id: str | None = None
    turn_id: str | None = None
    approval_needed: bool = False
    pending_request_id: str | None = None
    last_summary: str = ""
    response_text: str = ""
    raw_response_text: str = ""
    render_kind: str = "single_text"
    structured_output: dict[str, Any] | None = None
    primary_output: str = ""
    selected_output_label: str = ""
    selected_output_text: str = ""
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    trace: list[TraceEntry] = Field(default_factory=list)

    @classmethod
    def create(cls, *, source: SourceMetadata, prompt: str) -> "RunRecord":
        return cls(run_id=f"run-{uuid4().hex[:12]}", source=source, prompt=prompt)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def append_transcript(
        self, *, kind: str, message: str, payload: dict[str, Any] | None = None
    ) -> None:
        self.transcript.append(TranscriptEntry(kind=kind, message=message, payload=payload))
        self.touch()

    def append_response_delta(self, delta: str) -> None:
        self.raw_response_text += delta
        self.response_text += delta
        self.touch()

    def start_response_message(self) -> None:
        self.response_text = ""
        self.touch()

    def complete_response_message(self, text: str) -> None:
        self.response_text = text
        if not self.raw_response_text:
            self.raw_response_text = text
        self.touch()

    def append_trace(
        self,
        *,
        kind: str,
        label: str,
        tool_name: str | None = None,
        status: str | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        self.trace.append(
            TraceEntry(
                kind=kind,
                label=label,
                tool_name=tool_name,
                status=status,
                duration_ms=duration_ms,
                error=error,
            )
        )
        self.touch()

    def mark_status(self, status: RunStatus, *, summary: str | None = None) -> None:
        self.status = status
        if summary is not None:
            self.last_summary = summary
        self.touch()
