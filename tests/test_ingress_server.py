import json
from urllib import request

from ai_tools.codex_bridge.models import SourceMetadata
from ai_tools.ingress.server import LocalIngressServer


class StubService:
    def __init__(self, *, submit_error: Exception | None = None, ready: bool = True) -> None:
        self.submissions: list[tuple[SourceMetadata, str]] = []
        self.submit_error = submit_error
        self.ready = ready

    def submit_run(self, source: SourceMetadata, prompt: str):
        if self.submit_error is not None:
            raise self.submit_error
        self.submissions.append((source, prompt))
        return type("Run", (), {"run_id": "run-123"})()

    def list_runs(self):
        return []

    def current_run(self):
        return None

    def readiness(self):
        if self.ready:
            return {"ready": True, "code": "ready", "message": "bridge ready"}
        return {"ready": False, "code": "state_unwritable", "message": "state path is not writable"}


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
    assert json.loads(current.read().decode("utf-8")) == {"run": None}


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
