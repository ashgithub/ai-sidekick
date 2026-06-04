import json
from datetime import timedelta

from ai_tools.codex_bridge.models import RunRecord, RunStatus, SourceMetadata, utc_now
from ai_tools.codex_bridge.service import CodexBridgeService
from ai_tools.codex_bridge.state import ActiveRunStateStore


class FakeClient:
    def __init__(self) -> None:
        self.initialized = False
        self.thread_start_calls: list[dict] = []
        self.turn_start_calls: list[dict] = []
        self.turn_steer_calls: list[dict] = []
        self.turn_interrupt_calls: list[dict] = []
        self.approval_calls: list[tuple[str, object]] = []
        self.command_available = True
        self.fail_ensure: Exception | None = None

    def ensure_started(self) -> None:
        if self.fail_ensure is not None:
            raise self.fail_ensure
        self.initialized = True

    def thread_start(self, params: dict) -> dict:
        self.thread_start_calls.append(params)
        return {"thread": {"id": f"thread-{len(self.thread_start_calls)}"}}

    def turn_start(self, params: dict) -> dict:
        self.turn_start_calls.append(params)
        return {"turnId": f"turn-{len(self.turn_start_calls)}"}

    def turn_steer(self, params: dict) -> dict:
        self.turn_steer_calls.append(params)
        return {"turnId": params.get("turnId", "turn-1")}

    def turn_interrupt(self, params: dict) -> dict:
        self.turn_interrupt_calls.append(params)
        return {}

    def reply_to_server_request(self, request_id: str, payload: object) -> None:
        self.approval_calls.append((request_id, payload))

    def validate_command(self) -> tuple[bool, str]:
        if self.command_available:
            return True, "codex command is executable"
        return False, "codex command is not executable"


class FakeNotifier:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def run_started(self, title: str, message: str) -> None:
        self.events.append(("started", title))

    def run_completed(self, title: str, message: str) -> None:
        self.events.append(("completed", title))

    def approval_needed(self, title: str, message: str) -> None:
        self.events.append(("approval", title))

    def run_failed(self, title: str, message: str) -> None:
        self.events.append(("failed", title))


def test_submit_run_creates_thread_and_turn_and_marks_run_running() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())

    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Summarize this task",
    )

    assert client.initialized is True
    assert client.thread_start_calls
    assert client.turn_start_calls[0]["threadId"] == "thread-1"
    assert run.thread_id == "thread-1"
    assert run.status is RunStatus.RUNNING
    assert notifier.events[0] == ("started", "Run started")
    assert [entry.kind for entry in run.trace[:4]] == ["accepted", "codex_started", "thread_started", "turn_started"]


def test_submit_run_records_startup_failure_as_failed_run() -> None:
    client = FakeClient()
    client.fail_ensure = RuntimeError("app-server exited")
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())

    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Prompt",
    )

    assert run.status is RunStatus.FAILED
    assert run.last_summary == "app-server exited"
    assert run.trace[-1].kind == "failed"
    assert service.current_run() == run
    assert notifier.events == [("failed", "Run failed")]


def test_ai_tools_codex_json_completion_preserves_structured_output_shape() -> None:
    service = CodexBridgeService(client=FakeClient(), notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="ai_tools", source_label="Slack", source_id="ai-tools-1"),
        prompt="AI Tools request",
    )
    payload = {
        "render_kind": "text_pair",
        "primary_output": "Rewritten text",
        "structured_output": {"corrected": "Corrected text", "rewritten": "Rewritten text"},
    }
    service.handle_notification(
        {
            "method": "item/completed",
            "params": {"threadId": "thread-1", "item": {"type": "agentMessage", "text": json.dumps(payload)}},
        }
    )

    service.handle_notification(
        {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "status": "completed", "lastAgentMessage": "Done"},
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.status is RunStatus.COMPLETED
    assert refreshed.render_kind == "text_pair"
    assert refreshed.structured_output == {"corrected": "Corrected text", "rewritten": "Rewritten text"}
    assert refreshed.primary_output == "Rewritten text"
    assert refreshed.response_text == "Rewritten text"
    assert refreshed.selected_output_label == "Rewritten"


def test_select_run_output_updates_primary_text_for_alternatives() -> None:
    service = CodexBridgeService(client=FakeClient(), notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = RunRecord.create(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-1"),
        prompt="list files",
    )
    run.render_kind = "alternatives"
    run.structured_output = {
        "alternatives": [
            {"value": "ls", "explanation": "basic"},
            {"value": "ls -la", "explanation": "detailed"},
        ]
    }
    run.primary_output = "ls"
    run.response_text = "ls"
    service.store.upsert(run)

    updated = service.select_run_output(run.run_id, output_key="alternative:1")

    assert updated.primary_output == "ls -la"
    assert updated.response_text == "ls -la"
    assert updated.selected_output_label == "Alternative 2"
    assert updated.selected_output_text == "ls -la"
    assert updated.trace[-1].kind == "output_selected"


def test_select_run_output_updates_primary_text_for_text_pair() -> None:
    service = CodexBridgeService(client=FakeClient(), notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = RunRecord.create(
        source=SourceMetadata(source_kind="ai_tools", source_label="Slack", source_id="ai-tools-1"),
        prompt="fix this",
    )
    run.render_kind = "text_pair"
    run.structured_output = {"corrected": "Corrected text", "rewritten": "Rewritten text"}
    run.primary_output = "Rewritten text"
    run.response_text = "Rewritten text"
    service.store.upsert(run)

    updated = service.select_run_output(run.run_id, output_key="corrected")

    assert updated.primary_output == "Corrected text"
    assert updated.response_text == "Corrected text"
    assert updated.selected_output_label == "Corrected"


def test_select_run_output_can_apply_user_edited_text() -> None:
    service = CodexBridgeService(client=FakeClient(), notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = RunRecord.create(
        source=SourceMetadata(source_kind="ai_tools", source_label="Slack", source_id="ai-tools-1"),
        prompt="fix this",
    )
    run.render_kind = "text_pair"
    run.structured_output = {"corrected": "Corrected text", "rewritten": "Rewritten text"}
    run.primary_output = "Rewritten text"
    run.response_text = "Rewritten text"
    service.store.upsert(run)

    updated = service.select_run_output(run.run_id, output_key="rewritten", selected_text="Edited Slack text")

    assert updated.primary_output == "Edited Slack text"
    assert updated.response_text == "Edited Slack text"
    assert updated.selected_output_label == "Rewritten"
    assert updated.trace[-1].kind == "output_selected"


def test_server_approval_request_marks_run_as_attention_needed() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="slack", source_label="Slack", source_id="slack-1"),
        prompt="Do Slack work",
    )

    service.handle_server_request(
        {
            "id": "approval-1",
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thread-1", "turnId": "turn-1", "command": ["git", "status"], "cwd": "/tmp/demo"},
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.status is RunStatus.APPROVAL_NEEDED
    assert refreshed.approval_needed is True
    assert refreshed.pending_request_id == "approval-1"
    assert notifier.events[-1] == ("approval", "Approval needed")


def test_approve_run_replies_to_pending_server_request_and_clears_flag() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Do work",
    )
    service.handle_server_request(
        {
            "id": "approval-1",
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thread-1", "turnId": "turn-1", "command": ["git", "status"], "cwd": "/tmp/demo"},
        }
    )

    updated = service.approve_run(run.run_id)

    assert client.approval_calls == [("approval-1", {"decision": "accept"})]
    assert updated.approval_needed is False
    assert updated.status is RunStatus.RUNNING


def test_abort_running_run_interrupts_current_turn_and_marks_cancelled() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Do work",
    )

    updated = service.abort_run(run.run_id)

    assert client.turn_interrupt_calls == [{"threadId": "thread-1", "turnId": "turn-1"}]
    assert updated.status is RunStatus.CANCELLED
    assert updated.last_summary == "Aborted by user"
    assert updated.trace[-1].kind == "cancelled"
    assert notifier.events[-1] == ("failed", "Run aborted")


def test_abort_structured_ai_tools_run_without_codex_turn_marks_cancelled() -> None:
    service = CodexBridgeService(client=FakeClient(), notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = RunRecord.create(
        source=SourceMetadata(source_kind="ai_tools", source_label="AI Tools", source_id="ai-tools-1"),
        prompt="fix this",
    )
    run.mark_status(RunStatus.RUNNING, summary="AI Tools request running")
    service.store.upsert(run)

    updated = service.abort_run(run.run_id)

    assert updated.status is RunStatus.CANCELLED
    assert updated.last_summary == "Aborted by user"
    assert updated.thread_id is None
    assert updated.turn_id is None


def test_abort_pending_approval_cancels_request_without_extra_interrupt() -> None:
    client = FakeClient()
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Do work",
    )
    service.handle_server_request(
        {
            "id": "approval-1",
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thread-1", "turnId": "turn-1", "command": ["git", "status"], "cwd": "/tmp/demo"},
        }
    )

    updated = service.abort_run(run.run_id)

    assert client.approval_calls == [("approval-1", {"decision": "cancel"})]
    assert client.turn_interrupt_calls == []
    assert updated.approval_needed is False
    assert updated.pending_request_id is None
    assert updated.status is RunStatus.CANCELLED


def test_completed_notification_updates_summary_and_status() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Do work",
    )

    service.handle_notification(
        {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "status": "completed", "lastAgentMessage": "Done"},
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.status is RunStatus.COMPLETED
    assert refreshed.last_summary == "Done"
    assert notifier.events[-1] == ("completed", "Run completed")
    assert refreshed.trace[-1].kind == "completed"


def test_interrupted_turn_completion_marks_run_cancelled() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Do work",
    )

    service.handle_notification(
        {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "status": "interrupted", "summary": "Interrupted"},
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.status is RunStatus.CANCELLED
    assert refreshed.last_summary == "Interrupted"
    assert refreshed.trace[-1].kind == "cancelled"


def test_agent_message_keeps_raw_stream_but_promotes_latest_completed_answer() -> None:
    client = FakeClient()
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Do work",
    )

    service.handle_notification(
        {
            "method": "item/agentMessage/delta",
            "params": {"threadId": "thread-1", "delta": "I am checking context."},
        }
    )
    service.handle_notification(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thread-1",
                "item": {"type": "agentMessage", "text": "I am checking context."},
            },
        }
    )
    service.handle_notification(
        {
            "method": "item/started",
            "params": {"threadId": "thread-1", "item": {"type": "agentMessage"}},
        }
    )
    service.handle_notification(
        {
            "method": "item/agentMessage/delta",
            "params": {"threadId": "thread-1", "delta": "Final answer:\n- First point\n- Second point"},
        }
    )
    service.handle_notification(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thread-1",
                "item": {"type": "agentMessage", "text": "Final answer:\n- First point\n- Second point"},
            },
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.raw_response_text == "I am checking context.Final answer:\n- First point\n- Second point"
    assert refreshed.response_text == "Final answer:\n- First point\n- Second point"
    assert "I am checking context.Final answer" not in refreshed.response_text


def test_next_agent_delta_after_completed_message_starts_a_new_readable_answer() -> None:
    client = FakeClient()
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Do work",
    )
    service.handle_notification(
        {
            "method": "item/agentMessage/delta",
            "params": {"threadId": "thread-1", "delta": "I am checking context."},
        }
    )
    service.handle_notification(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thread-1",
                "item": {"type": "agentMessage", "text": "I am checking context."},
            },
        }
    )

    service.handle_notification(
        {
            "method": "item/agentMessage/delta",
            "params": {"threadId": "thread-1", "delta": "Final answer"},
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.raw_response_text == "I am checking context.Final answer"
    assert refreshed.response_text == "Final answer"


def test_blocked_agent_message_marks_run_failed() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="slack", source_label="Slack", source_id="slack-1"),
        prompt="Do Slack work",
    )

    service.handle_notification(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "item": {
                    "type": "agentMessage",
                    "text": "[from codex :bot:] :warning: Blocked\nI could not complete the unread-email lookup because no email connector was allowed.",
                },
            },
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.status is RunStatus.FAILED
    assert "Blocked" in refreshed.last_summary
    assert notifier.events[-1] == ("failed", "Run failed")


def test_not_found_agent_message_marks_run_not_found_after_completion() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="slack", source_label="Slack", source_id="slack-1"),
        prompt="Do Slack work",
    )
    service.handle_notification(
        {
            "method": "item/agentMessage/delta",
            "params": {"threadId": "thread-1", "delta": "No `@codex` message from Ashish found."},
        }
    )

    service.handle_notification(
        {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "status": "completed", "lastAgentMessage": "Run completed"},
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.status is RunStatus.NOT_FOUND
    assert refreshed.last_summary == "No @codex message found"
    assert notifier.events[-1] == ("failed", "Run needs attention")
    assert refreshed.trace[-1].kind == "not_found"


def test_stale_agent_message_marks_run_stale_after_completion() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="slack", source_label="Slack", source_id="slack-1"),
        prompt="Do Slack work",
    )
    service.handle_notification(
        {
            "method": "item/agentMessage/delta",
            "params": {
                "threadId": "thread-1",
                "delta": "Stale @codex message found; latest is older than 30 minutes.",
            },
        }
    )

    service.handle_notification(
        {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "status": "completed", "lastAgentMessage": "Run completed"},
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.status is RunStatus.STALE_SOURCE
    assert refreshed.last_summary == "Stale @codex message found"
    assert notifier.events[-1] == ("failed", "Run needs attention")
    assert refreshed.trace[-1].kind == "stale_source"


def test_new_submit_replaces_previous_active_run() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    first = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="First prompt",
    )
    second = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-2"),
        prompt="Second prompt",
    )
    assert service.get_run(first.run_id) is None
    assert service.get_run(second.run_id) is not None
    assert [run.run_id for run in service.list_runs()] == [second.run_id]


def test_steer_current_run_appends_to_active_turn_without_new_thread() -> None:
    client = FakeClient()
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Initial prompt",
    )

    steered = service.steer_current_run("Focus on the latest error")

    assert steered.run_id == run.run_id
    assert client.thread_start_calls == [{"cwd": str(service.cwd), "approvalPolicy": "on-request", "approvalsReviewer": "auto_review", "personality": "pragmatic"}]
    assert client.turn_start_calls == [
        {"threadId": "thread-1", "input": [{"type": "text", "text": "Initial prompt"}], "cwd": str(service.cwd)}
    ]
    assert client.turn_steer_calls == [
        {"threadId": "thread-1", "turnId": "turn-1", "input": [{"type": "text", "text": "Focus on the latest error"}]}
    ]
    assert steered.status is RunStatus.RUNNING
    assert steered.trace[-1].kind == "steered"
    assert steered.transcript[-1].kind == "user"
    assert steered.transcript[-1].message == "Focus on the latest error"


def test_continue_current_thread_starts_new_turn_without_new_thread() -> None:
    client = FakeClient()
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Initial prompt",
    )
    service.handle_notification(
        {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "status": "completed", "lastAgentMessage": "Done"},
        }
    )

    continued = service.continue_current_thread("Now write tests")

    assert continued.run_id == run.run_id
    assert len(client.thread_start_calls) == 1
    assert client.turn_start_calls[-1] == {
        "threadId": "thread-1",
        "input": [{"type": "text", "text": "Now write tests"}],
        "cwd": str(service.cwd),
    }
    assert continued.turn_id == "turn-2"
    assert continued.status is RunStatus.RUNNING
    assert continued.response_text == ""
    assert continued.raw_response_text == ""
    assert continued.trace[-1].kind == "continued"


def test_submit_to_current_thread_routes_by_intent() -> None:
    client = FakeClient()
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())

    first = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="AI Tools", source_id="ai-tools-1"),
        prompt="Initial task",
        intent="new",
    )
    steered = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="AI Tools", source_id="ai-tools-1"),
        prompt="Steer while running",
        intent="steer",
    )

    assert first.run_id == steered.run_id
    assert client.turn_steer_calls


def test_reuse_intent_uses_stable_thread_key_without_replacing_current_run_context() -> None:
    client = FakeClient()
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())

    first = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-1"),
        prompt="Explain first error",
        intent="reuse",
        thread_key="ai_tools:explain:ghostty",
    )
    service.handle_notification(
        {
            "method": "turn/completed",
            "params": {"threadId": first.thread_id, "status": "completed", "lastAgentMessage": "Done"},
        }
    )
    second = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-2"),
        prompt="Explain next error",
        intent="reuse",
        thread_key="ai_tools:explain:ghostty",
    )

    assert first.run_id != second.run_id
    assert first.thread_id == "thread-1"
    assert second.thread_id == "thread-1"
    assert len(client.thread_start_calls) == 1
    assert client.turn_start_calls[-1]["threadId"] == "thread-1"
    assert service.get_run(first.run_id) is None
    assert service.get_run(second.run_id) is not None


def test_reuse_intent_starts_distinct_threads_for_distinct_tool_keys() -> None:
    client = FakeClient()
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())

    explain = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-1"),
        prompt="Explain error",
        intent="reuse",
        thread_key="ai_tools:explain:ghostty",
    )
    proofread = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="Slack", source_id="ai-tools-2"),
        prompt="Fix text",
        intent="reuse",
        thread_key="ai_tools:slack:slack",
    )

    assert explain.thread_id == "thread-1"
    assert proofread.thread_id == "thread-2"
    assert len(client.thread_start_calls) == 2


def test_reuse_intent_resets_thread_after_max_turns() -> None:
    client = FakeClient()
    service = CodexBridgeService(
        client=client,
        notifier=FakeNotifier(),
        store=ActiveRunStateStore(),
        reusable_thread_max_turns=2,
    )

    first = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-1"),
        prompt="Explain first error",
        intent="reuse",
        thread_key="ai_tools:explain:ghostty",
    )
    second = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-2"),
        prompt="Explain second error",
        intent="reuse",
        thread_key="ai_tools:explain:ghostty",
    )
    third = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-3"),
        prompt="Explain third error",
        intent="reuse",
        thread_key="ai_tools:explain:ghostty",
    )

    assert first.thread_id == "thread-1"
    assert second.thread_id == "thread-1"
    assert third.thread_id == "thread-2"
    assert len(client.thread_start_calls) == 2
    assert third.trace[-2].kind == "thread_started"


def test_reuse_intent_resets_thread_after_max_age() -> None:
    client = FakeClient()
    service = CodexBridgeService(
        client=client,
        notifier=FakeNotifier(),
        store=ActiveRunStateStore(),
        reusable_thread_max_age_seconds=60,
    )

    first = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-1"),
        prompt="Explain first error",
        intent="reuse",
        thread_key="ai_tools:explain:ghostty",
    )
    service._reusable_threads["ai_tools:explain:ghostty"].created_at = utc_now() - timedelta(seconds=61)
    second = service.submit_or_route(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-2"),
        prompt="Explain second error",
        intent="reuse",
        thread_key="ai_tools:explain:ghostty",
    )

    assert first.thread_id == "thread-1"
    assert second.thread_id == "thread-2"
    assert len(client.thread_start_calls) == 2


def test_tool_call_notifications_add_trace_entries() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Prompt",
    )

    service.handle_notification(
        {
            "method": "item/started",
            "params": {
                "threadId": "thread-1",
                "item": {"type": "mcpToolCall", "id": "tool-1", "tool": "slack_search", "status": "inProgress"},
            },
        }
    )
    service.handle_notification(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thread-1",
                "item": {"type": "mcpToolCall", "id": "tool-1", "tool": "slack_search", "status": "completed"},
            },
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert [(entry.kind, entry.tool_name, entry.status) for entry in refreshed.trace[-2:]] == [
        ("tool_started", "slack_search", "inProgress"),
        ("tool_completed", "slack_search", "completed"),
    ]
    assert refreshed.trace[-1].duration_ms is not None


def test_auto_approval_review_notifications_add_trace_entries() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Prompt",
    )

    service.handle_notification(
        {
            "method": "item/autoApprovalReview/started",
            "params": {"threadId": "thread-1", "turnId": "turn-1"},
        }
    )
    service.handle_notification(
        {
            "method": "item/autoApprovalReview/completed",
            "params": {"threadId": "thread-1", "turnId": "turn-1"},
        }
    )

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert [entry.kind for entry in refreshed.trace[-2:]] == [
        "approval_started",
        "approval_completed",
    ]


def test_notification_without_thread_id_does_not_bleed_into_active_run() -> None:
    client = FakeClient()
    notifier = FakeNotifier()
    service = CodexBridgeService(client=client, notifier=notifier, store=ActiveRunStateStore())
    run = service.submit_run(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Prompt",
    )

    service.handle_notification({"method": "warning", "params": {"message": "ignore me"}})

    refreshed = service.get_run(run.run_id)
    assert refreshed is not None
    assert refreshed.transcript == run.transcript
    assert refreshed.response_text == ""


def test_readiness_reports_ready_when_state_and_codex_command_are_available(tmp_path) -> None:
    client = FakeClient()
    store_path = tmp_path / "run-state.json"
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())
    service.store_state_path = store_path

    assert service.readiness() == {
        "ready": True,
        "code": "ready",
        "message": "bridge ready",
    }


def test_readiness_reports_unready_when_codex_command_is_missing(tmp_path) -> None:
    client = FakeClient()
    client.command_available = False
    service = CodexBridgeService(client=client, notifier=FakeNotifier(), store=ActiveRunStateStore())
    service.store_state_path = tmp_path / "run-state.json"

    assert service.readiness() == {
        "ready": False,
        "code": "codex_unavailable",
        "message": "codex command is not executable",
    }


def test_panel_mode_persists_after_show_and_hide() -> None:
    class FakePanelController:
        def __init__(self) -> None:
            self.panel_mode = "rewrite"
            self.visible = False

        def show(self, mode: str | None = None) -> dict[str, object]:
            if mode in {"ask", "rewrite"}:
                self.panel_mode = mode
            self.visible = True
            return {"visible": self.visible, "panel_mode": self.panel_mode}

        def hide(self) -> dict[str, object]:
            self.visible = False
            return {"visible": self.visible, "panel_mode": self.panel_mode}

    service = CodexBridgeService(
        client=FakeClient(),
        notifier=FakeNotifier(),
        store=ActiveRunStateStore(),
        panel_controller=FakePanelController(),
    )

    assert service.panel_mode() == "rewrite"
    assert service.show_panel(mode="ask") == {"visible": True, "panel_mode": "ask"}
    assert service.panel_mode() == "ask"
    assert service.hide_panel() == {"visible": False, "panel_mode": "ask"}
    assert service.panel_mode() == "ask"
    assert service.show_panel(mode="unknown") == {"visible": True, "panel_mode": "ask"}
