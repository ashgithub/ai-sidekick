"""Resident bridge service coordinating runs and Codex app-server calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from ai_tools.ingress.prompt_contract import ai_tools_schema_example

from .models import RunRecord, RunStatus, SourceMetadata, utc_now
from .notifications import NullNotifier
from .protocol import CodexAppServerClient
from .state import ActiveRunStateStore


@dataclass
class ReusableThread:
    thread_id: str
    created_at: datetime
    turn_count: int = 0


class CodexBridgeService:
    def __init__(
        self,
        *,
        client: CodexAppServerClient | Any,
        notifier: object | None = None,
        store: ActiveRunStateStore | None = None,
        cwd: Path | None = None,
        thread_options: dict[str, Any] | None = None,
        panel_controller: object | None = None,
        reusable_thread_max_turns: int = 20,
        reusable_thread_max_age_seconds: int = 3600,
    ) -> None:
        self.client = client
        self.notifier = notifier or NullNotifier()
        self.store = store or ActiveRunStateStore()
        self.cwd = cwd or Path.cwd()
        self.thread_options = thread_options or {}
        self.panel_controller = panel_controller
        self.reusable_thread_max_turns = reusable_thread_max_turns
        self.reusable_thread_max_age_seconds = reusable_thread_max_age_seconds
        self._active_run_id: str | None = None
        self._thread_to_run_id: dict[str, str] = {}
        self._reusable_threads: dict[str, ReusableThread] = {}
        self._tool_started_at: dict[str, Any] = {}
        self._completed_agent_message_threads: set[str] = set()
        self._panel_mode = "rewrite"
        if hasattr(self.client, "set_notification_handler"):
            self.client.set_notification_handler(self.handle_notification)
        if hasattr(self.client, "set_server_request_handler"):
            self.client.set_server_request_handler(self.handle_server_request)

    def submit_run(self, *, source: SourceMetadata, prompt: str, thread_key: str | None = None) -> RunRecord:
        run = RunRecord.create(source=source, prompt=prompt)
        run.append_trace(kind="accepted", label=f"Accepted {source.source_label} request")
        run.mark_status(RunStatus.STARTING, summary="Starting run")
        run.append_transcript(kind="user", message=prompt)
        self.store.upsert(run)
        self._active_run_id = run.run_id

        try:
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
            reusable_thread = self._usable_reusable_thread(thread_key)
            if reusable_thread:
                reusable_thread.turn_count += 1
                run.thread_id = reusable_thread.thread_id
                run.append_trace(kind="thread_reused", label=f"Reused Codex thread: {thread_key}")
            else:
                thread_response = self.client.thread_start(thread_params)
                run.thread_id = thread_response["thread"]["id"]
                run.append_trace(kind="thread_started", label="Codex thread started")
                if thread_key:
                    self._reusable_threads[thread_key] = ReusableThread(
                        thread_id=run.thread_id,
                        created_at=utc_now(),
                        turn_count=1,
                    )
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
        except Exception as exc:  # noqa: BLE001
            message = str(exc) or type(exc).__name__
            run.mark_status(RunStatus.FAILED, summary=message)
            run.append_trace(kind="failed", label=message, error=type(exc).__name__)
            self.store.upsert(run)
            self.notifier.run_failed("Run failed", message)
        return run

    def _usable_reusable_thread(self, thread_key: str | None) -> ReusableThread | None:
        if not thread_key:
            return None
        reusable_thread = self._reusable_threads.get(thread_key)
        if reusable_thread is None:
            return None
        if self.reusable_thread_max_turns > 0 and reusable_thread.turn_count >= self.reusable_thread_max_turns:
            self._reusable_threads.pop(thread_key, None)
            return None
        if self.reusable_thread_max_age_seconds > 0:
            age_seconds = (utc_now() - reusable_thread.created_at).total_seconds()
            if age_seconds >= self.reusable_thread_max_age_seconds:
                self._reusable_threads.pop(thread_key, None)
                return None
        return reusable_thread

    def submit_or_route(
        self,
        *,
        source: SourceMetadata,
        prompt: str,
        intent: str = "new",
        thread_key: str | None = None,
    ) -> RunRecord:
        normalized = (intent or "new").strip().lower()
        if normalized == "new":
            return self.submit_run(source=source, prompt=prompt)
        if normalized == "reuse":
            return self.submit_run(source=source, prompt=prompt, thread_key=thread_key)
        if normalized == "steer":
            return self.steer_current_run(prompt)
        if normalized == "continue":
            return self.continue_current_thread(prompt)
        if normalized == "auto":
            current = self.current_run()
            if current is None or not current.thread_id:
                return self.submit_run(source=source, prompt=prompt)
            if current.status in {RunStatus.QUEUED, RunStatus.STARTING, RunStatus.RUNNING, RunStatus.APPROVAL_NEEDED}:
                return self.steer_current_run(prompt)
            return self.continue_current_thread(prompt)
        raise ValueError(f"Unknown invocation intent: {intent}")

    def steer_current_run(self, prompt: str) -> RunRecord:
        run = self._require_current_thread()
        if not run.turn_id:
            raise ValueError(f"Run {run.run_id} has no active turn to steer")
        self.client.turn_steer(
            {
                "threadId": run.thread_id,
                "turnId": run.turn_id,
                "input": [{"type": "text", "text": prompt}],
            }
        )
        run.append_transcript(kind="user", message=prompt)
        run.append_trace(kind="steered", label="Steered active turn")
        run.mark_status(RunStatus.RUNNING, summary="Steering run")
        self.store.upsert(run)
        return run

    def continue_current_thread(self, prompt: str) -> RunRecord:
        run = self._require_current_thread()
        turn_response = self.client.turn_start(
            {
                "threadId": run.thread_id,
                "input": [{"type": "text", "text": prompt}],
                "cwd": str(self.cwd),
            }
        )
        if "turnId" in turn_response:
            run.turn_id = turn_response["turnId"]
        run.approval_needed = False
        run.pending_request_id = None
        run.response_text = ""
        run.raw_response_text = ""
        run.append_transcript(kind="user", message=prompt)
        run.append_trace(kind="continued", label="Started follow-up turn")
        run.mark_status(RunStatus.RUNNING, summary="Continuing thread")
        self.store.upsert(run)
        self.notifier.run_started("Run started", "A Codex follow-up is now running.")
        return run

    def panel_mode(self) -> str:
        return self._panel_mode

    def show_panel(self, mode: str | None = None) -> dict[str, object]:
        self._set_panel_mode(mode)
        if self.panel_controller is not None and hasattr(self.panel_controller, "show"):
            return self._sync_panel_result(self.panel_controller.show(mode=self._panel_mode))
        return {"visible": False, "available": False, "panel_mode": self._panel_mode}

    def toggle_panel(self, mode: str | None = None) -> dict[str, object]:
        self._set_panel_mode(mode)
        if self.panel_controller is not None and hasattr(self.panel_controller, "toggle"):
            return self._sync_panel_result(self.panel_controller.toggle(mode=self._panel_mode))
        return {"visible": False, "available": False, "panel_mode": self._panel_mode}

    def hide_panel(self) -> dict[str, object]:
        if self.panel_controller is not None and hasattr(self.panel_controller, "hide"):
            return self._sync_panel_result(self.panel_controller.hide())
        return {"visible": False, "available": False, "panel_mode": self._panel_mode}

    def _set_panel_mode(self, mode: str | None) -> str:
        normalized = (mode or "").strip().lower()
        if normalized in {"ask", "rewrite"}:
            self._panel_mode = normalized
        return self._panel_mode

    def _sync_panel_result(self, result: dict[str, object]) -> dict[str, object]:
        result_mode = result.get("panel_mode")
        if isinstance(result_mode, str):
            self._set_panel_mode(result_mode)
        result["panel_mode"] = self._panel_mode
        return result

    def select_run_output(self, run_id: str, *, output_key: str, selected_text: str | None = None) -> RunRecord:
        run = self._require_run(run_id)
        label, text = self._resolve_output_selection(run, output_key)
        if selected_text is not None:
            if selected_text.strip():
                if selected_text != text:
                    raise ValueError("Edited output must be reviewed before applying to source")
                text = selected_text
        run.primary_output = text
        run.response_text = text
        run.selected_output_label = label
        run.selected_output_text = text
        run.append_trace(kind="output_selected", label=f"Selected output: {label}")
        self.store.upsert(run)
        return run

    def review_run_output(self, run_id: str, *, output_key: str, edited_text: str) -> RunRecord:
        run = self._require_run(run_id)
        label, original_text = self._resolve_output_selection(run, output_key)
        draft = edited_text.strip()
        if not draft:
            raise ValueError("Edited output is empty")
        if edited_text == original_text:
            raise ValueError("Output is unchanged; apply it directly")
        if not run.thread_id:
            raise ValueError(f"Run {run.run_id} has no thread")

        prompt = self._review_edited_output_prompt(
            run=run,
            selected_label=label,
            original_text=original_text,
            edited_text=edited_text,
        )
        turn_response = self.client.turn_start(
            {
                "threadId": run.thread_id,
                "input": [{"type": "text", "text": prompt}],
                "cwd": str(self.cwd),
            }
        )
        if "turnId" in turn_response:
            run.turn_id = turn_response["turnId"]
        run.approval_needed = False
        run.pending_request_id = None
        run.response_text = ""
        run.raw_response_text = ""
        run.primary_output = ""
        run.selected_output_text = ""
        run.append_transcript(kind="user", message=prompt)
        run.append_trace(kind="output_review_requested", label=f"Review edited output: {label}")
        run.mark_status(RunStatus.RUNNING, summary="Reviewing edited output")
        self.store.upsert(run)
        self.notifier.run_started("Run started", "Reviewing edited output.")
        return run

    def _review_edited_output_prompt(
        self,
        *,
        run: RunRecord,
        selected_label: str,
        original_text: str,
        edited_text: str,
    ) -> str:
        lines = [
            "Review edited AI Tools output. Do one task on the edited draft only. Return JSON only.",
            "",
            "Output:",
            ai_tools_schema_example(run.render_kind),
            "",
        ]
        if run.prompt_instructions:
            lines.extend(["Instructions:", run.prompt_instructions, ""])
        if run.app_context:
            lines.append(f"App context: {run.app_context}")
        if run.nudge:
            lines.append(f"Nudge: {run.nudge}")
        if run.app_context or run.nudge:
            lines.append("")
        if run.display_input_text:
            lines.extend(["Original input:", run.display_input_text, ""])
        lines.extend(
            [
                f"Selected output: {selected_label}",
                "",
                "Original selected output:",
                original_text,
                "",
                "Edited draft:",
                edited_text.strip(),
            ]
        )
        return "\n".join(lines).strip()

    def _default_output_label(self, run: RunRecord) -> str:
        if run.render_kind == "text_pair":
            return "Rewritten"
        if run.render_kind == "alternatives":
            return "Alternative 1"
        return "Answer"

    def _resolve_output_selection(self, run: RunRecord, output_key: str) -> tuple[str, str]:
        structured = run.structured_output or {}
        normalized = output_key.strip().lower()
        if run.render_kind == "text_pair":
            if normalized not in {"rewritten", "corrected"}:
                raise ValueError(f"Unknown text output key: {output_key}")
            value = str(structured.get(normalized, "")).strip()
            if not value:
                raise ValueError(f"Text output is empty: {output_key}")
            return normalized.capitalize(), value

        if run.render_kind == "alternatives" and normalized.startswith("alternative:"):
            raw_index = normalized.split(":", 1)[1]
            try:
                index = int(raw_index)
            except ValueError as exc:
                raise ValueError(f"Invalid alternative index: {raw_index}") from exc
            alternatives = structured.get("alternatives")
            if not isinstance(alternatives, list) or index < 0 or index >= len(alternatives):
                raise ValueError(f"Alternative index out of range: {index}")
            selected = alternatives[index]
            if not isinstance(selected, dict):
                raise ValueError(f"Alternative is not structured: {index}")
            value = str(selected.get("value", "")).strip()
            if not value:
                raise ValueError(f"Alternative output is empty: {index}")
            return f"Alternative {index + 1}", value

        if normalized in {"primary", "answer"}:
            value = (run.primary_output or run.response_text).strip()
            if not value:
                raise ValueError("Primary output is empty")
            return "Answer", value

        raise ValueError(f"Unknown output key: {output_key}")

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

    def update_run_metadata(self, run_id: str, **metadata: Any) -> RunRecord:
        run = self._require_run(run_id)
        for field, value in metadata.items():
            if hasattr(run, field):
                setattr(run, field, value)
        self.store.upsert(run)
        return run

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

    def abort_run(self, run_id: str) -> RunRecord:
        run = self._require_run(run_id)
        terminal = {
            RunStatus.COMPLETED,
            RunStatus.CANCELLED,
            RunStatus.FAILED,
            RunStatus.NOT_FOUND,
            RunStatus.STALE_SOURCE,
        }
        if run.status in terminal:
            return run

        if run.pending_request_id:
            self.client.reply_to_server_request(run.pending_request_id, {"decision": "cancel"})
        else:
            if not run.thread_id or not run.turn_id:
                run.append_trace(kind="cancel_requested", label="No Codex turn; marking local run cancelled")
            else:
                self.client.turn_interrupt({"threadId": run.thread_id, "turnId": run.turn_id})

        run.pending_request_id = None
        run.approval_needed = False
        run.mark_status(RunStatus.CANCELLED, summary="Aborted by user")
        run.append_trace(kind="cancelled", label="Aborted by user")
        run.append_transcript(kind="event", message="abort")
        self.store.upsert(run)
        self.notifier.run_failed("Run aborted", "A Codex task was aborted.")
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
                thread_id = params.get("threadId") if isinstance(params, dict) else None
                if isinstance(thread_id, str) and thread_id in self._completed_agent_message_threads:
                    run.start_response_message()
                    self._completed_agent_message_threads.discard(thread_id)
                if not run.raw_response_text:
                    run.append_trace(kind="first_response", label="First response token")
                run.append_response_delta(delta)
                run.append_transcript(kind="assistant", message=delta, payload=params if isinstance(params, dict) else None)
        elif method == "item/started":
            item = params.get("item", {}) if isinstance(params, dict) else {}
            if isinstance(item, dict):
                if item.get("type") == "agentMessage":
                    thread_id = params.get("threadId") if isinstance(params, dict) else None
                    if isinstance(thread_id, str):
                        self._completed_agent_message_threads.discard(thread_id)
                    run.start_response_message()
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
                    run.complete_response_message(text)
                    thread_id = params.get("threadId") if isinstance(params, dict) else None
                    if isinstance(thread_id, str):
                        self._completed_agent_message_threads.add(thread_id)
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
                or ("Interrupted" if status == "interrupted" else "Run completed")
            )
            if status == "completed":
                if run.source.source_kind == "ai_tools":
                    self._apply_ai_tools_structured_response(run)
                outcome = self._classify_completed_outcome(run.response_text or run.raw_response_text)
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
            elif status == "interrupted":
                already_cancelled = run.status is RunStatus.CANCELLED
                run.pending_request_id = None
                run.approval_needed = False
                run.mark_status(RunStatus.CANCELLED, summary=summary or "Interrupted")
                run.append_trace(kind="cancelled", label=summary or "Interrupted")
                if not already_cancelled:
                    self.notifier.run_failed("Run aborted", summary or "Interrupted")
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

    def _require_current_thread(self) -> RunRecord:
        run = self.current_run()
        if run is None:
            raise ValueError("No current run is available")
        if not run.thread_id:
            raise ValueError(f"Run {run.run_id} has no thread")
        return run

    def _classify_completed_outcome(self, response_text: str) -> RunStatus | None:
        if "No `@codex` message from Ashish found." in response_text:
            return RunStatus.NOT_FOUND
        if "Stale @codex message found" in response_text:
            return RunStatus.STALE_SOURCE
        return None

    def _apply_ai_tools_structured_response(self, run: RunRecord) -> None:
        raw_text = (run.response_text or run.raw_response_text).strip()
        if not raw_text:
            return

        try:
            payload = self._parse_json_object(raw_text)
        except ValueError:
            run.render_kind = "single_text"
            run.structured_output = {"text": raw_text}
            run.primary_output = raw_text
            run.selected_output_label = "Answer"
            run.selected_output_text = raw_text
            return

        render_kind = str(payload.get("render_kind") or "single_text").strip()
        structured = payload.get("structured_output")
        if not isinstance(structured, dict):
            structured = {}
        primary = str(payload.get("primary_output") or "").strip()

        if render_kind == "text_pair":
            corrected = str(structured.get("corrected", "")).strip()
            rewritten = str(structured.get("rewritten", "")).strip()
            if not primary:
                primary = rewritten or corrected
            structured = {"corrected": corrected, "rewritten": rewritten}
        elif render_kind == "alternatives":
            alternatives = structured.get("alternatives")
            if not isinstance(alternatives, list):
                alternatives = []
            normalized_alternatives: list[dict[str, str]] = []
            for item in alternatives[:3]:
                if isinstance(item, dict):
                    value = str(item.get("value", "")).strip()
                    explanation = str(item.get("explanation", "")).strip()
                    if value:
                        normalized_alternatives.append({"value": value, "explanation": explanation})
            if not primary and normalized_alternatives:
                primary = normalized_alternatives[0]["value"]
            structured = {"alternatives": normalized_alternatives}
        else:
            render_kind = "single_text"
            text = str(structured.get("text") or primary or raw_text).strip()
            primary = primary or text
            structured = {"text": text}

        run.render_kind = render_kind
        run.structured_output = structured
        run.primary_output = primary or raw_text
        run.response_text = run.primary_output
        run.selected_output_label = self._default_output_label(run)
        run.selected_output_text = run.primary_output
        run.append_trace(kind="structured_output", label=f"Parsed AI Tools output: {render_kind}")

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("No JSON object found") from exc
            payload = json.loads(cleaned[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("JSON response is not an object")
        return payload

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
