from ai_tools.codex_bridge.models import RunRecord, RunStatus, SourceMetadata
from ai_tools.web_panel.ui_bridge import PanelUiBridge


class StubService:
    def __init__(self) -> None:
        source = SourceMetadata(source_kind="manual", source_label="Manual", source_id="manual-1")
        self.run = RunRecord.create(source=source, prompt="hello")
        self.run.status = RunStatus.RUNNING
        self.run.last_summary = "Working"
        self.submissions: list[tuple[str, str]] = []

    def list_runs(self):
        return [self.run]

    def current_run(self):
        return self.run

    def get_run(self, run_id: str):
        return self.run if run_id == self.run.run_id else None

    def submit_or_route(self, *, source, prompt: str, intent: str = "new"):
        self.submissions.append((prompt, intent))
        return self.run


def test_ui_bridge_returns_snapshot_for_panel_rendering() -> None:
    bridge = PanelUiBridge(service=StubService())

    snapshot = bridge.get_snapshot()

    assert snapshot["runs"][0]["status"] == "running"
    assert snapshot["runs"][0]["last_summary"] == "Working"
    assert snapshot["runs"][0]["prompt_text"] == "hello"
    assert snapshot["runs"][0]["response_text"] == ""
    assert snapshot["runs"][0]["trace_entries"] == []
    assert snapshot["current_run"]["run_id"] == snapshot["runs"][0]["run_id"]


def test_ui_bridge_submits_to_current_thread_with_intent() -> None:
    service = StubService()
    bridge = PanelUiBridge(service=service)

    payload = bridge.submit_prompt("keep going", intent="steer")

    assert payload["run_id"] == service.run.run_id
    assert service.submissions == [("keep going", "steer")]
