"""Live terminal progress for ``yta run`` — renders engine ProgressEvents.

This is the rich-aware renderer the engine knows nothing about: the CLI passes
``ProgressDisplay.handle`` as the engine's progress callback, and hands the
display itself to a rich ``Live`` region. ``__rich__`` recomputes elapsed time
on every refresh, so running actions tick in place without a manual ticker.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from youtrack_aitrack.domain.progress import ProgressEvent

_OUTCOME_STYLE: dict[str, tuple[str, str]] = {
    "ok": ("✓", "green"),
    "fail": ("✗", "red"),
    "skipped": ("·", "yellow"),
}


@dataclass
class _Row:
    workflow: str
    action_id: str
    is_hook: bool
    phase: str = "queued"  # queued | running | done
    outcome: str | None = None
    started_at: float | None = None
    duration_ms: int | None = None


class ProgressDisplay:
    def __init__(self, *, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self._rows: dict[tuple[str, str], _Row] = {}

    def handle(self, event: ProgressEvent) -> None:
        key = (event.workflow_name, event.action_id)
        row = self._rows.get(key)
        if row is None:
            row = _Row(event.workflow_name, event.action_id, event.is_hook)
            self._rows[key] = row
        if event.phase == "queued":
            row.phase = "queued"
        elif event.phase == "started":
            row.phase = "running"
            row.started_at = self._now()
        elif event.phase == "finished":
            row.phase = "done"
            row.outcome = event.outcome
            row.duration_ms = event.duration_ms

    def _elapsed_s(self, row: _Row) -> float | None:
        if row.phase == "running" and row.started_at is not None:
            return self._now() - row.started_at
        if row.phase == "done" and row.duration_ms is not None:
            return row.duration_ms / 1000
        return None

    def snapshot(self) -> list[tuple[str, str, str, str]]:
        """(workflow, label, status, elapsed) per row — the testable view of state."""
        rows = []
        for row in self._rows.values():
            status = row.outcome or "done" if row.phase == "done" else row.phase
            status = "pending" if status == "queued" else status
            rows.append((row.workflow, _label(row), status, _fmt_mmss(self._elapsed_s(row))))
        return rows

    def __rich__(self) -> Table:
        table = Table.grid(padding=(0, 2))
        table.add_column()  # workflow
        table.add_column()  # status glyph / spinner
        table.add_column()  # action label
        table.add_column(justify="right")  # elapsed
        for row in self._rows.values():
            elapsed = _fmt_mmss(self._elapsed_s(row))
            table.add_row(row.workflow, _status_cell(row), _label(row), elapsed)
        return table


def _label(row: _Row) -> str:
    return f"{row.action_id} (hook)" if row.is_hook else row.action_id


def _status_cell(row: _Row) -> Text | Spinner:
    if row.phase == "running":
        return Spinner("dots", text="running")
    if row.phase == "done":
        glyph, style = _OUTCOME_STYLE.get(row.outcome or "", ("•", "white"))
        return Text(f"{glyph} {row.outcome or 'done'}", style=style)
    return Text("· pending", style="dim")


def _fmt_mmss(seconds: float | None) -> str:
    if seconds is None:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"
