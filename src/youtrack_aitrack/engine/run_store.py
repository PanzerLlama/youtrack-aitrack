"""RunStore Protocol — persists RunReport history and the polling cursor."""

from __future__ import annotations

from typing import Protocol

from youtrack_aitrack.domain.run import RunReport


class RunStore(Protocol):
    def save_run(self, report: RunReport) -> None: ...

    def load_run(self, run_id: str) -> RunReport | None: ...

    def save_cursor(self, token: str | None) -> None: ...

    def load_cursor(self) -> str | None: ...


class _InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunReport] = {}
        self._cursor: str | None = None

    def save_run(self, report: RunReport) -> None:
        self._runs[report.run_id] = report

    def load_run(self, run_id: str) -> RunReport | None:
        return self._runs.get(run_id)

    def save_cursor(self, token: str | None) -> None:
        self._cursor = token

    def load_cursor(self) -> str | None:
        return self._cursor
