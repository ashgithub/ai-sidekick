"""Transient active-run state for the local companion."""

from __future__ import annotations

from .models import RunRecord


class ActiveRunStateStore:
    def __init__(self) -> None:
        self._current_run: RunRecord | None = None

    def upsert(self, run: RunRecord) -> RunRecord:
        self._current_run = run.model_copy(deep=True)
        return self._current_run

    def get_current_run(self) -> RunRecord | None:
        return self._current_run.model_copy(deep=True) if self._current_run else None

    def get_run(self, run_id: str) -> RunRecord | None:
        run = self.get_current_run()
        if run is None or run.run_id != run_id:
            return None
        return run

    def list_runs(self) -> list[RunRecord]:
        run = self.get_current_run()
        return [run] if run is not None else []

    def assert_writable(self) -> None:
        return None
