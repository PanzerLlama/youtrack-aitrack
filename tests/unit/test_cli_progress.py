"""Tests for the ProgressDisplay terminal renderer (no live terminal needed)."""

from __future__ import annotations

import io

from rich.console import Console

from youtrack_aitrack.cli.progress import ProgressDisplay, _fmt_mmss
from youtrack_aitrack.domain.progress import ActionOutcome, ProgressEvent, ProgressPhase


def _ev(
    action: str,
    phase: ProgressPhase,
    *,
    is_hook: bool = False,
    outcome: ActionOutcome | None = None,
    duration_ms: int | None = None,
) -> ProgressEvent:
    return ProgressEvent(
        workflow_name="wf",
        action_id=action,
        phase=phase,
        is_hook=is_hook,
        outcome=outcome,
        duration_ms=duration_ms,
    )


def test_queued_running_done_transitions() -> None:
    clock = [100.0]
    display = ProgressDisplay(now=lambda: clock[0])

    display.handle(_ev("a", "queued"))
    assert display.snapshot() == [("wf", "a", "pending", "")]

    display.handle(_ev("a", "started"))
    clock[0] = 162.0  # 62s elapsed while running
    assert display.snapshot() == [("wf", "a", "running", "1:02")]

    display.handle(_ev("a", "finished", outcome="ok", duration_ms=62000))
    assert display.snapshot() == [("wf", "a", "ok", "1:02")]


def test_finished_uses_duration_not_wall_clock() -> None:
    clock = [0.0]
    display = ProgressDisplay(now=lambda: clock[0])
    display.handle(_ev("a", "started"))
    display.handle(_ev("a", "finished", outcome="ok", duration_ms=48000))
    clock[0] = 9999.0  # time moves on; a finished row must not keep ticking
    assert display.snapshot()[0] == ("wf", "a", "ok", "0:48")


def test_hook_label_and_skipped_outcome() -> None:
    display = ProgressDisplay()
    display.handle(_ev("notify", "finished", is_hook=True, outcome="skipped", duration_ms=0))
    workflow, label, status, elapsed = display.snapshot()[0]
    assert (workflow, label, status, elapsed) == ("wf", "notify (hook)", "skipped", "0:00")


def test_rows_preserve_insertion_order() -> None:
    display = ProgressDisplay()
    for aid in ("first", "second", "third"):
        display.handle(_ev(aid, "queued"))
    assert [label for _, label, _, _ in display.snapshot()] == ["first", "second", "third"]


def test_fmt_mmss() -> None:
    assert _fmt_mmss(None) == ""
    assert _fmt_mmss(0) == "0:00"
    assert _fmt_mmss(9) == "0:09"
    assert _fmt_mmss(83) == "1:23"
    assert _fmt_mmss(3725) == "62:05"


def test_rich_render_does_not_raise() -> None:
    display = ProgressDisplay()
    display.handle(_ev("a", "started"))
    display.handle(_ev("b", "finished", outcome="ok", duration_ms=1200))
    console = Console(file=io.StringIO(), force_terminal=True, width=80)
    console.print(display)
    out = console.file.getvalue()
    assert "a" in out and "b" in out
