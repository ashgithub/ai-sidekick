"""Manual ingress helpers for local synthetic runs."""

from __future__ import annotations

from ai_tools.codex_bridge.models import SourceMetadata


def manual_source_metadata(source_id: str = "manual") -> SourceMetadata:
    return SourceMetadata(source_kind="manual", source_label="Manual", source_id=source_id)
