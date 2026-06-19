"""``youtrack-aitrack run`` — manually dispatch workflows for one issue."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import typer
from rich.live import Live

from youtrack_aitrack.cli.progress import ProgressDisplay
from youtrack_aitrack.config import (
    InstanceConfigError,
    load_instance_config,
)
from youtrack_aitrack.domain.run import ActionResult, RunReport, RunState
from youtrack_aitrack.runtime import Runner, build_runner

# YouTrack issue IDs are <PROJECT>-<NUMBER> where project is alphanumeric and
# starts with a letter. We validate at the CLI boundary so the value can never
# be interpreted as a git flag or a URL path component.
_ISSUE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")

_ISSUE_ID_ARG = typer.Argument(..., help="YouTrack issue id, e.g. DEMO-42.")
_WORKFLOW_OPTION = typer.Option(
    None, "--workflow", help="Limit dispatch to a single workflow name."
)
_DRY_RUN_OPTION = typer.Option(
    False, "--dry-run", help="Run workflows but skip YouTrack field writes and comments."
)
_FORCE_OPTION = typer.Option(False, "--force", help="Bypass idempotency dedup for this dispatch.")
_REPO_DIR_OPTION = typer.Option(
    None, "--repo-dir", help="Git repo root (default: current working directory)."
)
_STUB_LLM_OPTION = typer.Option(
    False,
    "--stub-llm",
    help="Substitute a placeholder for every Anthropic call (zero LLM cost).",
)


def run_command(
    ctx: typer.Context,
    issue_id: str = _ISSUE_ID_ARG,
    workflow: str | None = _WORKFLOW_OPTION,
    dry_run: bool = _DRY_RUN_OPTION,
    force: bool = _FORCE_OPTION,
    repo_dir: Path | None = _REPO_DIR_OPTION,
    stub_llm: bool = _STUB_LLM_OPTION,
) -> None:
    """Dispatch workflows for ISSUE_ID matching its current state."""
    if not _ISSUE_ID_RE.match(issue_id):
        raise typer.BadParameter(
            f"invalid issue id {issue_id!r}; expected <PROJECT>-<NUMBER>, e.g. DEMO-42"
        )
    config_dir: Path = ctx.obj["config_dir"]
    config_yaml = config_dir / "config.yaml"
    if not config_yaml.is_file():
        raise typer.BadParameter(f"no config.yaml at {config_yaml}; run 'init' first.")
    try:
        config = load_instance_config(config_yaml)
    except InstanceConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc

    runner = build_runner(
        config,
        config_dir,
        repo_dir=repo_dir,
        dry_run=dry_run,
        stub_llm=stub_llm,
        workflow_names={workflow} if workflow is not None else None,
    )
    reports = _dispatch(runner, issue_id, force=force)
    _print_summary(reports)
    if any(r.state is RunState.FAILED for r in reports):
        raise typer.Exit(code=1)


def _dispatch(runner: Runner, issue_id: str, *, force: bool) -> list[RunReport]:
    """Run the workflows, showing a live progress region on an interactive TTY.

    Non-TTY callers (tests, pipes, daemons) skip the rich Live region and run
    plainly — the final summary is the persistent record either way.
    """
    if not sys.stdout.isatty():
        return asyncio.run(runner.run(issue_id, force=force))
    return asyncio.run(_dispatch_live(runner, issue_id, force=force))


async def _dispatch_live(runner: Runner, issue_id: str, *, force: bool) -> list[RunReport]:
    """Drive a rich Live region from the asyncio loop itself.

    ``auto_refresh`` is off so refresh runs in this single event-loop thread —
    the same thread the progress callback mutates state on — instead of rich's
    background thread, which would race ``__rich__`` against ``handle``.
    """
    display = ProgressDisplay()
    with Live(display, auto_refresh=False, transient=True) as live:

        async def tick() -> None:
            while True:
                live.refresh()
                await asyncio.sleep(0.25)

        ticker = asyncio.create_task(tick())
        try:
            reports = await runner.run(issue_id, force=force, on_progress=display.handle)
        finally:
            ticker.cancel()
            await asyncio.gather(ticker, return_exceptions=True)
            live.refresh()
    return reports


def _print_summary(reports: list[RunReport]) -> None:
    if not reports:
        typer.echo("No matching workflows.")
        return
    typer.echo(f"{'WORKFLOW':<28} {'ACTION':<28} {'STATE':<8} {'TIME':>8}  NOTE")
    for report in reports:
        for result in report.action_results:
            typer.echo(_format_row(report.workflow_name, result, hook=False))
        for hook in report.hook_results:
            typer.echo(_format_row(report.workflow_name, hook, hook=True))
        typer.echo(f"=== {report.workflow_name}: {report.state.value.upper()}")


def _format_row(workflow_name: str, result: ActionResult, *, hook: bool) -> str:
    state = "skipped" if result.skipped else ("ok" if result.success else "fail")
    full_note = result.skip_reason or result.error or ""
    note = full_note.splitlines()[0] if full_note else ""
    if "\n" in full_note:
        note += " (see run report for full error)"
    label = f"{result.action_id} (hook)" if hook else result.action_id
    time_col = _fmt_duration_ms(result.duration_ms)
    return f"{workflow_name:<28} {label:<28} {state:<8} {time_col:>8}  {note}"


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
