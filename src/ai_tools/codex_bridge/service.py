"""Resident bridge service coordinating runs and Codex app-server calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import RunRecord, RunStatus, SourceMetadata
from .notifications import NullNotifier
from .protocol import CodexAppServerClient
from .state import ActiveRunStateStore


class CodexBridgeService:
    def __init__(
        self,
        *,
        client: CodexAppServerClient | Any,
        notifier: object | None = None,
        store: ActiveRunStateStore | None = None,
        cwd: Path | None = None,
        thread_options: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.notifier = notifier or NullNotifier()
        self.store = store or ActiveRunStateStore()
        self.cwd = cwd or Path.cwd()
        self.thread_options = thread_options or {}
        self._active_run_id: str | None = None
        self._thread_to_run_id: dict[str, str] = {}
        self._tool_started_at: dict[str, Any] = {}
        if hasattr(self.client, "set_notification_handler"):
            self.client.set_notification_handler(self.handle_notification)
        if hasattr(self.client, "set_server_request_handler"):
            self.client.set_server_request_handler(self.handle_server_request)

    def submit_run(self, *, source: SourceMetadata, prompt: str) -> RunRecord:
        run = RunRecord.create(source=source, prompt=prompt)
        run.append_trace(kind="accepted", label=f"Accepted {source.source_label} request")
        run.mark_status(RunStatus.STARTING, summary="Starting run")
        run.append_transcript(kind="user", message=prompt)
        self.store.upsert(run)
        self._active_run_id = run.run_id

        self.client.ensure_started()
        run.append_trace(kind="codex_started", label="Codex app-server ready")
        self.store.upsert(run)
        thread_params = {
            "cwd": str(self.cwd),
            "approvalPolicy": "on-request",
            "approvalsReviewer": "auto_review",
            "personality": "pragmatic",
        }
        thread_params.update(self.thread_options)
        thread_response = self.client.thread_start(thread_params)
        run.thread_id = thread_response["thread"]["id"]
        run.append_trace(kind="thread_started", label="Codex thread started")
        self._thread_to_run_id[run.thread_id] = run.run_id
        turn_response = self.client.turn_start(
            {
                "threadId": run.thread_id,
                "input": [{"type": "text", "text": prompt}],
                "cwd": str(self.cwd),
            }
        )
        if "turnId" in turn_response:
            run.turn_id = turn_response["turnId"]
        run.append_trace(kind="turn_started", label="Codex turn started")
        run.mark_status(RunStatus.RUNNING, summary="Run started")
        self.store.upsert(run)
        self.notifier.run_started("Run started", "A Codex task is now running.")
        return run

    def readiness(self) -> dict[str, object]:
        if hasattr(self.store, "assert_writable"):
            try:
                self.store.assert_writable()
            except OSError as exc:
                return {
                    "ready": False,
                    "code": "state_unwritable",
                    "message": str(exc),
                }

        if hasattr(self.client, "validate_command"):
            command_ok, command_message = self.client.validate_command()
            if not command_ok:
                return {
                    "ready": False,
                    "code": "codex_unavailable",
                    "message": command_message,
                }

        return {
            "ready": True,
            "code": "ready",
            "message": "bridge ready",
        }

    def list_runs(self) -> list[RunRecord]:
        return self.store.list_runs()

    def current_run(self) -> RunRecord | None:
        return self.store.get_current_run()

    def get_run(self, run_id: str) -> RunRecord | None:
        return self.store.get_run(run_id)

    def approve_run(self, run_id: str) -> RunRecord:
        run = self._require_run(run_id)
        if not run.pending_request_id:
            raise ValueError(f"Run {run_id} has no pending approval request")
        self.client.reply_to_server_request(run.pending_request_id, {"decision": "accept"})
        run.pending_request_id = None
        run.approval_needed = False
        run.mark_status(RunStatus.RUNNING, summary="Approval granted")
        self.store.upsert(run)
        return run

    def deny_run(self, run_id: str) -> RunRecord:
        run = self._require_run(run_id)
        if not run.pending_request_id:
            raise ValueError(f"Run {run_id} has no pending approval request")
        self.client.reply_to_server_request(run.pending_request_id, {"decision": "decline"})
        run.pending_request_id = None
        run.approval_needed = False
        run.mark_status(RunStatus.FAILED, summary="Approval denied")
        self.store.upsert(run)
        self.notifier.run_failed("Run failed", "A Codex task was denied.")
        return run

    def handle_notification(self, payload: dict[str, Any]) -> None:
        method = str(payload.get("method", ""))
        params = payload.get("params", {})
        run = self._resolve_run_from_payload(params)
        if run is None:
            return
        if method == "turn/started":
            run.mark_status(RunStatus.RUNNING, summary="Turn started")
        elif method == "item/agentMessage/delta":
            delta = str(params.get("delta", ""))
            if delta:
                if not run.response_text:
                    run.append_trace(kind="first_response", label="First response token")
                run.append_response_delta(delta)
                run.append_transcript(kind="assistant", message=delta, payload=params if isinstance(params, dict) else None)
        elif method == "item/started":
            item = params.get("item", {}) if isinstance(params, dict) else {}
            if isinstance(item, dict):
                self._trace_item_started(run, item)
            run.append_transcript(kind="event", message=method, payload=params if isinstance(params, dict) else None)
        elif method == "item/completed":
            item = params.get("item", {}) if isinstance(params, dict) else {}
            item_type = item.get("type") if isinstance(item, dict) else None
            if isinstance(item, dict):
                self._trace_item_completed(run, item)
            if item_type == "agentMessage":
                text = str(item.get("text", ""))
                if text:
                    if not run.response_text:
                        run.response_text = text
                    blocked = text.startswith("[from codex :bot:] :warning: Blocked")
                    if blocked:
                        run.mark_status(RunStatus.FAILED, summary="Blocked")
                        self.notifier.run_failed("Run failed", "Blocked")
                run.append_transcript(kind="event", message=method, payload=params if isinstance(params, dict) else None)
            else:
                run.append_transcript(kind="event", message=method, payload=params if isinstance(params, dict) else None)
        elif method == "item/autoApprovalReview/started":
            run.append_trace(kind="approval_started", label="Auto approval review started")
            run.append_transcript(kind="event", message=method, payload=params if isinstance(params, dict) else None)
        elif method == "item/autoApprovalReview/completed":
            run.append_trace(kind="approval_completed", label="Auto approval review completed")
            run.append_transcript(kind="event", message=method, payload=params if isinstance(params, dict) else None)
        elif method == "turn/completed":
            turn = params.get("turn", {}) if isinstance(params, dict) else {}
            status = str(
                params.get("status")
                or (turn.get("status") if isinstance(turn, dict) else None)
                or "completed"
            )
            summary = str(
                params.get("lastAgentMessage")
                or params.get("summary")
                or (turn.get("summary") if isinstance(turn, dict) else None)
                or "Run completed"
            )
            if status == "completed":
                outcome = self._classify_completed_outcome(run.response_text)
                if outcome == RunStatus.NOT_FOUND:
                    run.mark_status(RunStatus.NOT_FOUND, summary="No @codex message found")
                    run.append_trace(kind="not_found", label="No @codex message found")
                    self.notifier.run_failed("Run needs attention", "No @codex message found.")
                elif outcome == RunStatus.STALE_SOURCE:
                    run.mark_status(RunStatus.STALE_SOURCE, summary="Stale @codex message found")
                    run.append_trace(kind="stale_source", label="Stale @codex message found")
                    self.notifier.run_failed("Run needs attention", "Stale @codex message found.")
                else:
                    run.mark_status(RunStatus.COMPLETED, summary=summary)
                    run.append_trace(kind="completed", label=summary)
                    self.notifier.run_completed("Run completed", summary)
            else:
                run.mark_status(RunStatus.FAILED, summary=summary)
                run.append_trace(kind="failed", label=summary)
                self.notifier.run_failed("Run failed", summary)
        else:
            run.append_transcript(kind="event", message=method, payload=params if isinstance(params, dict) else None)
        self.store.upsert(run)

    def handle_server_request(self, payload: dict[str, Any]) -> None:
        run = self._resolve_run_from_payload(payload.get("params", {}))
        if run is None:
            return
        run.pending_request_id = str(payload["id"])
        run.approval_needed = True
        run.mark_status(RunStatus.APPROVAL_NEEDED, summary="Approval needed")
        run.append_trace(kind="approval_started", label=str(payload.get("method", "approval")))
        run.append_transcript(kind="approval", message=str(payload.get("method", "approval")), payload=payload.get("params"))
        self.store.upsert(run)
        self.notifier.approval_needed("Approval needed", "A Codex task needs approval.")

    def _resolve_run_from_payload(self, payload: Any) -> RunRecord | None:
        if isinstance(payload, dict):
            thread_id = payload.get("threadId")
            if isinstance(thread_id, str) and thread_id in self._thread_to_run_id:
                return self.store.get_run(self._thread_to_run_id[thread_id])
        return None

    def _require_run(self, run_id: str) -> RunRecord:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(f"Unknown run_id: {run_id}")
        return run

    def _classify_completed_outcome(self, response_text: str) -> RunStatus | None:
        if "No `@codex` message from Ashish found." in response_text:
            return RunStatus.NOT_FOUND
        if "Stale @codex message found" in response_text:
            return RunStatus.STALE_SOURCE
        return None

    def _trace_item_started(self, run: RunRecord, item: dict[str, Any]) -> None:
        item_type = item.get("type")
        if item_type == "mcpToolCall":
            item_id = str(item.get("id", ""))
            tool_name = str(item.get("tool") or item.get("name") or "tool")
            if item_id:
                self._tool_started_at[item_id] = run.updated_at
            run.append_trace(
                kind="tool_started",
                label=f"Tool started: {tool_name}",
                tool_name=tool_name,
                status=str(item.get("status") or ""),
            )
        elif item_type == "autoApprovalReview":
            run.append_trace(kind="approval_started", label="Auto approval review started")

    def _trace_item_completed(self, run: RunRecord, item: dict[str, Any]) -> None:
        item_type = item.get("type")
        if item_type == "mcpToolCall":
            item_id = str(item.get("id", ""))
            tool_name = str(item.get("tool") or item.get("name") or "tool")
            duration_ms = None
            started_at = self._tool_started_at.pop(item_id, None) if item_id else None
            if started_at is not None:
                duration_ms = max(0, int((run.updated_at - started_at).total_seconds() * 1000))
            error = item.get("error")
            run.append_trace(
                kind="tool_completed",
                label=f"Tool completed: {tool_name}",
                tool_name=tool_name,
                status=str(item.get("status") or ""),
                duration_ms=duration_ms,
                error=str(error) if error else None,
            )
        elif item_type == "autoApprovalReview":
            run.append_trace(kind="approval_completed", label="Auto approval review completed")
