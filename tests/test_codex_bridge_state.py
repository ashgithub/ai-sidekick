from ai_tools.codex_bridge.models import RunRecord, RunStatus, SourceMetadata
from ai_tools.codex_bridge.state import ActiveRunStateStore


def test_active_store_keeps_only_current_run() -> None:
    store = ActiveRunStateStore()
    source = SourceMetadata(source_kind="slack", source_label="Slack", source_id="slack-1")
    first = RunRecord.create(source=source, prompt="first")
    first.status = RunStatus.RUNNING
    second = RunRecord.create(source=source, prompt="second")
    second.status = RunStatus.APPROVAL_NEEDED

    store.upsert(first)
    store.upsert(second)

    items = store.list_runs()

    assert len(items) == 1
    assert items[0].run_id == second.run_id
    assert items[0].status is RunStatus.APPROVAL_NEEDED
    assert store.get_run(first.run_id) is None
    assert store.get_current_run() is not None
    assert store.get_current_run().run_id == second.run_id
