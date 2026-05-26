"""UI-facing snapshot adapter for the web panel."""

from __future__ import annotations

from typing import Any


class PanelUiBridge:
    def __init__(self, *, service: Any) -> None:
        self.service = service

    def get_snapshot(self) -> dict[str, Any]:
        runs = [self._serialize_run(run) for run in self.service.list_runs()]
        current = self.service.current_run()
        return {"runs": runs, "current_run": self._serialize_run(current) if current else None}

    def submit_manual(self, prompt: str) -> dict[str, Any]:
        from ai_tools.ingress.manual import manual_source_metadata

        run = self.service.submit_run(source=manual_source_metadata("manual-ui"), prompt=prompt)
        return run.model_dump(mode="json")

    def approve_run(self, run_id: str) -> dict[str, Any]:
        run = self.service.approve_run(run_id)
        return run.model_dump(mode="json")

    def deny_run(self, run_id: str) -> dict[str, Any]:
        run = self.service.deny_run(run_id)
        return self._serialize_run(run)

    def _serialize_run(self, run: Any) -> dict[str, Any]:
        payload = run.model_dump(mode="json")
        payload["prompt_text"] = run.prompt
        payload["response_text"] = run.response_text
        payload["event_entries"] = [
            entry.model_dump(mode="json")
            for entry in run.transcript
            if entry.kind not in {"user", "assistant"}
        ]
        payload["response_entries"] = [
            entry.model_dump(mode="json")
            for entry in run.transcript
            if entry.kind == "assistant"
        ]
        payload["trace_entries"] = [entry.model_dump(mode="json") for entry in run.trace]
        return payload
