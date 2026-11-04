"""Snapshot of the yta run summary table with and without token/cost usage."""

from __future__ import annotations

import pytest

from youtrack_aitrack.cli.run_summary import print_summary
from youtrack_aitrack.domain.run import ActionResult, RunReport, RunState


def _report() -> RunReport:
    return RunReport(
        workflow_name="audit",
        state=RunState.DONE,
        action_results=[
            ActionResult(
                action_id="security_audit",
                success=True,
                duration_ms=62_000,
                output={
                    "text": "...",
                    "input_tokens": 41_312,
                    "output_tokens": 1_234,
                    "cost_usd": 0.1842,
                },
            ),
            ActionResult(
                action_id="pages_changed",
                success=True,
                duration_ms=900,
                output={"text": "...", "input_tokens": 512, "output_tokens": 4, "cost_usd": 0.0024},
            ),
            ActionResult(action_id="stubbed", success=True, duration_ms=10, output={"text": "x"}),
        ],
        hook_results=[ActionResult(action_id="done", success=True, duration_ms=120)],
    )


def test_summary_table_snapshot(capsys: pytest.CaptureFixture[str]) -> None:
    print_summary([_report()], [], issue_id="DEMO-1")

    lines = [line.rstrip() for line in capsys.readouterr().out.splitlines()]
    assert lines == [
        "WORKFLOW                     ACTION                       STATE        TIME"
        "       TOKENS     COST  NOTE",
        "audit                        security_audit               ok          1m02s"
        "   41.3k/1.2k  $0.1842",
        "audit                        pages_changed                ok          900ms"
        "        512/4  $0.0024",
        "audit                        stubbed                      ok           10ms",
        "audit                        done (hook)                  ok          120ms",
        "=== audit: DONE (cost $0.1866)",
    ]


def test_summary_footer_omits_cost_when_nothing_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = RunReport(
        workflow_name="wf",
        state=RunState.FAILED,
        action_results=[ActionResult(action_id="a", success=False, error="boom")],
    )
    print_summary([report], [], issue_id="DEMO-1")

    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "=== wf: FAILED"
    assert lines[1].rstrip().endswith("boom")
