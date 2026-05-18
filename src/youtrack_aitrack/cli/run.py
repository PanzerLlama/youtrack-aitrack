"""``youtrack-aitrack run`` — manually dispatch workflows for one issue."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import typer

from youtrack_aitrack.config import (
    InstanceConfigError,
    load_instance_config,
)
from youtrack_aitrack.domain.run import ActionResult, RunReport, RunState
from youtrack_aitrack.runtime import build_runner

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
    reports = asyncio.run(runner.run(issue_id, force=force))
    _print_summary(reports)
    if any(r.state is RunState.FAILED for r in reports):
        raise typer.Exit(code=1)


def _print_summary(reports: list[RunReport]) -> None:
    if not reports:
        typer.echo("No matching workflows.")
        return
    typer.echo(f"{'WORKFLOW':<32} {'ACTION':<32} {'STATE':<10} NOTE")
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
    return f"{workflow_name:<32} {label:<32} {state:<10} {note}"
