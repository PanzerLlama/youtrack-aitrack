"""``youtrack-aitrack workflows`` — list and validate workflow YAML files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from youtrack_aitrack.config import (
    InstanceConfigError,
    WorkflowParseError,
    load_instance_config,
    load_workflow,
)
from youtrack_aitrack.domain.workflow import Workflow

app = typer.Typer(
    name="workflows",
    help="Inspect and validate workflow YAML files in the config directory.",
    no_args_is_help=True,
)


@dataclass(frozen=True)
class _ScanResult:
    path: Path
    workflow: Workflow | None
    error: str | None


def _resolve_workflows_dir(config_dir: Path) -> Path:
    config_yaml = config_dir / "config.yaml"
    if not config_yaml.is_file():
        raise typer.BadParameter(f"no config.yaml at {config_yaml}; run 'init' first.")
    try:
        instance = load_instance_config(config_yaml)
    except InstanceConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc
    return instance.workflows_path(config_dir)


def _scan(workflows_dir: Path) -> list[_ScanResult]:
    if not workflows_dir.is_dir():
        return []
    results: list[_ScanResult] = []
    for yaml_path in sorted(workflows_dir.glob("*.yaml")):
        try:
            wf = load_workflow(yaml_path)
        except WorkflowParseError as exc:
            results.append(_ScanResult(yaml_path, None, str(exc)))
        else:
            results.append(_ScanResult(yaml_path, wf, None))
    return results


@app.command("list")
def list_command(ctx: typer.Context) -> None:
    """Print every workflow file with name, trigger type, and action count."""
    config_dir: Path = ctx.obj["config_dir"]
    workflows_dir = _resolve_workflows_dir(config_dir)
    results = _scan(workflows_dir)
    if not results:
        typer.echo(f"No workflows found in {workflows_dir}.")
        return
    typer.echo(f"{'FILE':<32} {'NAME':<32} {'TRIGGER':<20} ACTIONS")
    for r in results:
        if r.error is not None:
            typer.echo(f"ERROR: {r.path.name}: {r.error}")
            continue
        wf = r.workflow
        assert wf is not None
        typer.echo(f"{r.path.name:<32} {wf.name:<32} {wf.trigger.type:<20} {len(wf.actions)}")


@app.command("validate")
def validate_command(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Print each file as it is checked."
    ),
) -> None:
    """Exit non-zero if any workflow YAML fails to load. Quiet on success."""
    config_dir: Path = ctx.obj["config_dir"]
    workflows_dir = _resolve_workflows_dir(config_dir)
    results = _scan(workflows_dir)
    failures = [r for r in results if r.error is not None]
    if verbose:
        for r in results:
            status = "OK" if r.error is None else "FAIL"
            typer.echo(f"{status}: {r.path.name}")
    for r in failures:
        typer.echo(f"ERROR: {r.path.name}: {r.error}", err=True)
    if failures:
        raise typer.Exit(code=1)
    if verbose:
        typer.echo(f"{len(results)} workflow(s) OK.")
