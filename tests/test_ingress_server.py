import json
from pathlib import Path
from urllib.error import HTTPError
from urllib import request

from ai_tools.codex_bridge.models import RunRecord, RunStatus, SourceMetadata
from ai_tools.ingress.server import LocalIngressServer

ROOT = Path(__file__).resolve().parents[1]


class StubService:
    def __init__(
        self,
        *,
        submit_error: Exception | None = None,
        ready: bool = True,
        current_run: RunRecord | None = None,
    ) -> None:
        self.submissions: list[tuple[SourceMetadata, str]] = []
        self.routed_submissions: list[tuple[SourceMetadata, str, str]] = []
        self.panel_actions: list[str] = []
        self.abort_calls: list[str] = []
        self.select_calls: list[tuple[str, str, str | None]] = []
        self.review_calls: list[tuple[str, str, str]] = []
        self.submit_error = submit_error
        self.ready = ready
        self.thread_keys: list[str | None] = []
        self.current_run_record = current_run
        self.panel_mode_value = "rewrite"

    def submit_run(self, source: SourceMetadata, prompt: str):
        if self.submit_error is not None:
            raise self.submit_error
        self.submissions.append((source, prompt))
        return type("Run", (), {"run_id": "run-123"})()

    def submit_or_route(
        self,
        source: SourceMetadata,
        prompt: str,
        intent: str = "new",
        thread_key: str | None = None,
    ):
        self.routed_submissions.append((source, prompt, intent))
        self.thread_keys.append(thread_key)
        return type("Run", (), {"run_id": "run-routed"})()

    def panel_mode(self):
        return self.panel_mode_value

    def show_panel(self, mode: str | None = None):
        if mode in {"ask", "rewrite"}:
            self.panel_mode_value = mode
        self.panel_actions.append("show")
        return {"visible": True, "panel_mode": self.panel_mode_value}

    def toggle_panel(self, mode: str | None = None):
        if mode in {"ask", "rewrite"}:
            self.panel_mode_value = mode
        self.panel_actions.append("toggle")
        return {"visible": True, "panel_mode": self.panel_mode_value}

    def hide_panel(self):
        self.panel_actions.append("hide")
        return {"visible": False, "panel_mode": self.panel_mode_value}

    def abort_run(self, run_id: str):
        self.abort_calls.append(run_id)
        return type("Run", (), {"run_id": run_id, "status": type("Status", (), {"value": "cancelled"})()})()

    def select_run_output(self, run_id: str, *, output_key: str, selected_text: str | None = None):
        self.select_calls.append((run_id, output_key, selected_text))
        return type(
            "Run",
            (),
            {
                "run_id": run_id,
                "primary_output": selected_text or "ls -la",
                "selected_output_label": "Alternative 2",
            },
        )()

    def review_run_output(self, run_id: str, *, output_key: str, edited_text: str):
        self.review_calls.append((run_id, output_key, edited_text))
        return type(
            "Run",
            (),
            {
                "run_id": run_id,
                "status": type("Status", (), {"value": "running"})(),
            },
        )()

    def list_runs(self):
        return [self.current_run_record] if self.current_run_record else []

    def current_run(self):
        return self.current_run_record

    def get_run(self, run_id: str):
        if self.current_run_record and self.current_run_record.run_id == run_id:
            return self.current_run_record
        return None

    def readiness(self):
        if self.ready:
            return {"ready": True, "code": "ready", "message": "bridge ready"}
        return {"ready": False, "code": "state_unwritable", "message": "state path is not writable"}


class RejectingSelectionService(StubService):
    def select_run_output(self, run_id: str, *, output_key: str, selected_text: str | None = None):
        raise ValueError("Edited output must be reviewed before applying to source")


def test_ingress_server_accepts_slack_payload_and_reports_health() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        health = request.urlopen(f"http://127.0.0.1:{server.port}/healthz", timeout=2)
        payload = json.dumps(
            {
                "source_id": "slack-123",
                "source_label": "Slack",
                "prompt": "Investigate this request",
            }
        ).encode("utf-8")
        ingest = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/ingest/slack",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
    finally:
        server.stop()

    assert health.status == 200
    assert json.loads(ingest.read().decode("utf-8")) == {
        "run_id": "run-123",
        "status": "accepted",
        "panel_visibility": "manual",
    }
    assert service.submissions[0][0].source_kind == "slack"
    assert "# Slack Codex Worker" in service.submissions[0][1]
    assert "## Captured Hotkey Payload" in service.submissions[0][1]
    assert "Investigate this request" in service.submissions[0][1]
    assert "Maximum source age: 30 minutes" in service.submissions[0][1]


def test_ingress_server_reports_runs_api_for_readiness() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        runs = request.urlopen(f"http://127.0.0.1:{server.port}/api/runs", timeout=2)
    finally:
        server.stop()

    assert runs.status == 200
    assert json.loads(runs.read().decode("utf-8")) == {"runs": []}


def test_ingress_server_reports_current_run() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        current = request.urlopen(f"http://127.0.0.1:{server.port}/api/current-run", timeout=2)
    finally:
        server.stop()

    assert current.status == 200
    assert json.loads(current.read().decode("utf-8")) == {"run": None, "panel_mode": "rewrite"}


def test_ingress_server_omits_transcript_from_panel_run_snapshot() -> None:
    run = RunRecord.create(
        source=SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1"),
        prompt="Do work",
    )
    run.append_transcript(kind="assistant", message="streamed token", payload={"large": "metadata"})
    service = StubService(current_run=run)
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        current = request.urlopen(f"http://127.0.0.1:{server.port}/api/current-run", timeout=2)
    finally:
        server.stop()

    payload = json.loads(current.read().decode("utf-8"))
    assert payload["run"]["run_id"] == run.run_id
    assert "transcript" not in payload["run"]
    assert payload["panel_mode"] == "rewrite"


def test_event_stream_is_not_limited_to_one_hour() -> None:
    server_source = (ROOT / "src" / "ai_tools" / "ingress" / "server.py").read_text(encoding="utf-8")

    assert "range(7200)" not in server_source
    assert "while True:" in server_source
    assert ": keepalive" in server_source


def test_ingress_server_reports_readyz() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        ready = request.urlopen(f"http://127.0.0.1:{server.port}/readyz", timeout=2)
    finally:
        server.stop()

    assert ready.status == 200
    assert json.loads(ready.read().decode("utf-8")) == {
        "ready": True,
        "code": "ready",
        "message": "bridge ready",
    }


def test_ingress_server_reports_unready_as_json_error() -> None:
    service = StubService(ready=False)
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        try:
            request.urlopen(f"http://127.0.0.1:{server.port}/readyz", timeout=2)
        except request.HTTPError as exc:
            status = exc.code
            payload = json.loads(exc.read().decode("utf-8"))
        else:  # pragma: no cover - the assertion below documents the expected path
            raise AssertionError("expected /readyz to return HTTP 503")
    finally:
        server.stop()

    assert status == 503
    assert payload == {
        "ready": False,
        "code": "state_unwritable",
        "message": "state path is not writable",
    }


def test_ingress_server_returns_json_error_when_submit_crashes() -> None:
    service = StubService(submit_error=PermissionError("state path is not writable"))
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        payload = json.dumps(
            {
                "source_id": "slack-123",
                "source_label": "Slack",
                "prompt": "Investigate this request",
            }
        ).encode("utf-8")
        try:
            request.urlopen(
                request.Request(
                    f"http://127.0.0.1:{server.port}/ingest/slack",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=2,
            )
        except request.HTTPError as exc:
            status = exc.code
            payload = json.loads(exc.read().decode("utf-8"))
        else:  # pragma: no cover - the assertion below documents the expected path
            raise AssertionError("expected submit failure to return HTTP 500")
    finally:
        server.stop()

    assert status == 500
    assert payload == {
        "error": "submit_failed",
        "message": "state path is not writable",
        "detail": "PermissionError",
    }


def test_ingress_server_accepts_source_neutral_invocations() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        payload = json.dumps(
            {
                "source_kind": "ai_tools",
                "source_label": "AI Tools",
                "source_id": "ai-tools-1",
                "prompt": "Proofread this text",
                "intent": "continue",
            }
        ).encode("utf-8")
        response = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/api/invoke",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {
        "run_id": "run-routed",
        "status": "accepted",
        "panel_visibility": "manual",
    }
    source, prompt, intent = service.routed_submissions[0]
    assert source.source_kind == "ai_tools"
    assert source.source_label == "AI Tools"
    assert prompt == "Proofread this text"
    assert intent == "continue"


def test_ingress_server_accepts_structured_ai_tools_invocations() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        payload = json.dumps(
            {
                "source_kind": "ai_tools",
                "source_label": "Slack",
                "source_id": "ai-tools-1",
                "text": "pls fix this",
                "app_context": "Slack",
                "nudge": "slack",
                "intent": "reuse",
            }
        ).encode("utf-8")
        response = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/api/ai-tools",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {
        "run_id": "run-routed",
        "status": "accepted",
        "panel_visibility": "manual",
    }
    source, prompt, intent = service.routed_submissions[0]
    assert source.source_kind == "ai_tools"
    assert source.source_label == "Slack"
    assert intent == "reuse"
    assert "App context: Slack" in prompt
    assert "Nudge: slack" in prompt
    assert "pls fix this" in prompt
    assert "Return JSON only" in prompt
    assert service.thread_keys == ["ai_tools:slack:slack"]


def test_shortcut_endpoint_resolves_slack_profile_to_sidekick_review_action() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        response = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/api/shortcut",
                data=json.dumps(
                    {
                        "app": "Slack",
                        "text": "pls fix this",
                        "interaction": "replace-selection",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {
        "run_id": "run-routed",
        "status": "accepted",
        "client_action": "wait_for_sidekick",
        "poll_url": "/api/shortcut/results/run-routed",
        "panel_visibility": "manual",
    }
    source, prompt, intent = service.routed_submissions[0]
    assert source.source_kind == "ai_tools"
    assert source.source_label == "Slack"
    assert intent == "reuse"
    assert "App context: Slack" in prompt
    assert "Nudge: slack" in prompt
    assert service.thread_keys == ["ai_tools:slack:slack"]
    assert service.panel_actions == ["show"]


def test_shortcut_endpoint_resolves_terminal_profile_to_explain_poll_action() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        response = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/api/shortcut",
                data=json.dumps(
                    {
                        "app": "Ghostty",
                        "text": "explain this error",
                        "interaction": "replace-selection",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {
        "run_id": "run-routed",
        "status": "accepted",
        "client_action": "poll_and_replace",
        "poll_url": "/api/shortcut/results/run-routed",
        "panel_visibility": "manual",
    }
    source, prompt, intent = service.routed_submissions[0]
    assert source.source_label == "Ghostty"
    assert intent == "reuse"
    assert "App context: Ghostty" in prompt
    assert "Nudge: explain" in prompt
    assert service.thread_keys == ["ai_tools:explain:ghostty"]


def test_shortcut_endpoint_empty_text_opens_ask_mode_without_submitting() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        response = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/api/shortcut",
                data=json.dumps({"app": "Mail", "text": "", "interaction": "replace-selection"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {
        "status": "accepted",
        "client_action": "show_sidekick",
        "panel_visibility": "manual",
    }
    assert service.routed_submissions == []
    assert service.panel_actions == ["show"]
    assert service.panel_mode_value == "ask"


def test_shortcut_result_returns_ready_output_for_completed_run() -> None:
    run = RunRecord.create(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-1"),
        prompt="AI Tools request",
    )
    run.primary_output = "Use rg instead"
    run.response_text = "Use rg instead"
    run.mark_status(RunStatus.COMPLETED, summary="Done")
    service = StubService(current_run=run)
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        response = request.urlopen(f"http://127.0.0.1:{server.port}/api/shortcut/results/{run.run_id}", timeout=2)
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {"state": "ready", "output": "Use rg instead"}


def test_shortcut_result_returns_review_pending_until_sidekick_selection() -> None:
    run = RunRecord.create(
        source=SourceMetadata(source_kind="ai_tools", source_label="Slack", source_id="ai-tools-1"),
        prompt="AI Tools request",
    )
    run.mark_status(RunStatus.COMPLETED, summary="Done")
    service = StubService(current_run=run)
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        response = request.urlopen(
            f"http://127.0.0.1:{server.port}/api/shortcut/results/{run.run_id}?client_action=wait_for_sidekick",
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {
        "state": "review_pending",
        "retry_after_ms": 500,
        "message": "Review in sidekick, then Apply to source.",
    }


def test_shortcut_result_returns_failed_for_terminal_run_states() -> None:
    run = RunRecord.create(
        source=SourceMetadata(source_kind="ai_tools", source_label="Ghostty", source_id="ai-tools-1"),
        prompt="AI Tools request",
    )
    run.mark_status(RunStatus.FAILED, summary="Model failed")
    service = StubService(current_run=run)
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        response = request.urlopen(f"http://127.0.0.1:{server.port}/api/shortcut/results/{run.run_id}", timeout=2)
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {"state": "failed", "message": "Model failed"}


def test_ingress_server_exposes_panel_show_hide_and_toggle_actions() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        show = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/api/panel/show",
                data=json.dumps({"mode": "ask"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
        toggle = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/api/panel/toggle",
                data=json.dumps({"mode": "rewrite"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
        hide = request.urlopen(
            request.Request(f"http://127.0.0.1:{server.port}/api/panel/hide", data=b"{}", method="POST"),
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(show.read().decode("utf-8")) == {"visible": True, "panel_mode": "ask"}
    assert json.loads(toggle.read().decode("utf-8")) == {"visible": True, "panel_mode": "rewrite"}
    assert json.loads(hide.read().decode("utf-8")) == {"visible": False, "panel_mode": "rewrite"}
    assert service.panel_actions == ["show", "toggle", "hide"]


def test_ingress_server_exposes_run_abort_action() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        response = request.urlopen(
            request.Request(f"http://127.0.0.1:{server.port}/api/runs/run-123/abort", data=b"{}", method="POST"),
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {"run_id": "run-123", "status": "cancelled"}
    assert service.abort_calls == ["run-123"]


def test_ingress_server_exposes_run_output_selection_action() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        response = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/api/runs/run-123/select-output",
                data=json.dumps({"output_key": "alternative:1", "text": "  edited command\n"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {
        "run_id": "run-123",
        "primary_output": "  edited command\n",
        "selected_output_label": "Alternative 2",
    }
    assert service.select_calls == [("run-123", "alternative:1", "  edited command\n")]


def test_ingress_server_exposes_run_output_review_action() -> None:
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        response = request.urlopen(
            request.Request(
                f"http://127.0.0.1:{server.port}/api/runs/run-123/review-output",
                data=json.dumps({"output_key": "rewritten", "text": "Edited Slack text"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
    finally:
        server.stop()

    assert json.loads(response.read().decode("utf-8")) == {
        "run_id": "run-123",
        "status": "running",
    }
    assert service.review_calls == [("run-123", "rewritten", "Edited Slack text")]


def test_ingress_server_returns_bad_request_for_rejected_output_selection() -> None:
    service = RejectingSelectionService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0)

    try:
        server.start()
        try:
            request.urlopen(
                request.Request(
                    f"http://127.0.0.1:{server.port}/api/runs/run-123/select-output",
                    data=json.dumps({"output_key": "rewritten", "text": "Edited text"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=2,
            )
        except HTTPError as exc:
            response = exc
        else:
            raise AssertionError("rejected selection unexpectedly succeeded")
    finally:
        server.stop()

    assert response.code == 400
    assert json.loads(response.read().decode("utf-8")) == {
        "error": "selection_rejected",
        "message": "Edited output must be reviewed before applying to source",
    }


def test_static_assets_are_not_cached_between_sidekick_restarts(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "app.js").write_text('console.log("sidekick");', encoding="utf-8")
    service = StubService()
    server = LocalIngressServer(service=service, host="127.0.0.1", port=0, static_dir=static_dir)

    try:
        server.start()
        response = request.urlopen(f"http://127.0.0.1:{server.port}/static/app.js", timeout=2)
    finally:
        server.stop()

    assert response.headers["Cache-Control"] == "no-store, max-age=0"
