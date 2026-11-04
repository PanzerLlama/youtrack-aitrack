"""Final summary rendering for ``youtrack-aitrack run``."""

from __future__ import annotations

import typer

from youtrack_aitrack.domain.progress import WorkflowSkipped
from youtrack_aitrack.domain.run import ActionResult, RunReport


def print_repo_state(reports: list[RunReport], *, issue_id: str, pattern: str) -> None:
    """One line naming the branch and commit the run operated on (same for every report)."""
    if not reports:
        return
    first = reports[0]
    if first.branch is None:
        glob = pattern.replace("{task_id}", issue_id)
        typer.echo(
            f"branch: none (pattern {glob!r}); actions needing git_diff skip. "
            "Wrong repo? pass --repo-dir"
        )
        return
    sha = f" @ {first.commit_sha[:10]}" if first.commit_sha else ""
    typer.echo(f"branch: {first.branch}{sha}")


def print_summary(
    reports: list[RunReport], skipped: list[WorkflowSkipped], *, issue_id: str
) -> None:
    for skip in skipped:
        typer.echo(_format_skip(skip, issue_id))
    if not reports:
        if not skipped:
            typer.echo("No workflows configured.")
        elif all(s.reason == "already_dispatched" for s in skipped):
            typer.echo("Nothing to run: already dispatched. Re-run with --force.")
        else:
            typer.echo("No matching workflows.")
        return
    typer.echo(f"{'WORKFLOW':<28} {'ACTION':<28} {'STATE':<8} {'TIME':>8}  NOTE")
    for report in reports:
        for result in report.action_results:
            typer.echo(_format_row(report.workflow_name, result, hook=False))
        for hook in report.hook_results:
            typer.echo(_format_row(report.workflow_name, hook, hook=True))
        typer.echo(f"=== {report.workflow_name}: {report.state.value.upper()}")


def _format_skip(skip: WorkflowSkipped, issue_id: str) -> str:
    if skip.reason == "already_dispatched":
        return (
            f"{skip.workflow_name}: already dispatched for {issue_id} "
            f"(key {skip.idempotency_key}); skipped by idempotency"
        )
    return f"{skip.workflow_name}: trigger did not match the issue's current state"


def print_outputs(reports: list[RunReport]) -> None:
    for report in reports:
        for result in report.action_results:
            text = (result.output or {}).get("text")
            if isinstance(text, str) and text.strip():
                typer.echo(f"\n--- {report.workflow_name} / {result.action_id}\n{text.rstrip()}")


def _format_row(workflow_name: str, result: ActionResult, *, hook: bool) -> str:
    state = "skipped" if result.skipped else ("ok" if result.success else "fail")
    full_note = result.skip_reason or result.error or _success_note(result)
    note = full_note.splitlines()[0] if full_note else ""
    if "\n" in full_note:
        note += " (see run report for full error)"
    label = f"{result.action_id} (hook)" if hook else result.action_id
    time_col = _fmt_duration_ms(result.duration_ms)
    return f"{workflow_name:<28} {label:<28} {state:<8} {time_col:>8}  {note}"


def _success_note(result: ActionResult) -> str:
    """Actions may put a one-line human summary under output['note'] (e.g. branch created)."""
    note = (result.output or {}).get("note")
    return note if isinstance(note, str) else ""


def _fmt_duration_ms(ms: int | None) -> str:
    if ms is None:
        return ""
    if ms < 1000:
        return f"{ms}ms"
    secs = ms / 1000
    if secs < 60:
        return f"{secs:.1f}s"
    minutes, rem = divmod(int(secs), 60)
    return f"{minutes}m{rem:02d}s"
