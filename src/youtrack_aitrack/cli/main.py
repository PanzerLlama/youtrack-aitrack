"""CLI entry point for youtrack-aitrack."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from dotenv import load_dotenv

from youtrack_aitrack.cli.config_dir import resolve_config_dir
from youtrack_aitrack.cli.init import init_command
from youtrack_aitrack.cli.poll import poll_command
from youtrack_aitrack.cli.run import run_command
from youtrack_aitrack.cli.workflows import app as workflows_app


def _package_version() -> str:
    """Return the installed distribution's version, or 'unknown' if not installed.

    Sourcing from importlib.metadata keeps the CLI output in lockstep with
    pyproject.toml. The fallback covers in-tree imports during tests where
    the distribution may not be registered with the runtime's package index.
    """
    try:
        return version("youtrack-aitrack")
    except PackageNotFoundError:
        return "unknown"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"youtrack-aitrack {_package_version()}")
        raise typer.Exit()


app = typer.Typer(
    name="youtrack-aitrack",
    help="YAML-driven workflow engine for YouTrack AI-agent automations.",
    no_args_is_help=True,
)

_CONFIG_DIR_OPTION = typer.Option(
    None,
    "--config-dir",
    help="Override config dir (default: $YOUTRACK_AITRACK_HOME or ~/.youtrack-aitrack).",
)
_VERSION_OPTION = typer.Option(
    None,
    "--version",
    "-V",
    callback=_version_callback,
    is_eager=True,
    help="Print version and exit.",
)


@app.callback()
def _root(
    ctx: typer.Context,
    config_dir: Path | None = _CONFIG_DIR_OPTION,
    # is_eager=True means the callback fires before config_dir resolution,
    # so '--version' works even without a config dir present.
    show_version: bool | None = _VERSION_OPTION,
) -> None:
    """YAML-driven workflow engine for YouTrack AI-agent automations."""
    resolved = resolve_config_dir(config_dir)
    env_file = resolved / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = resolved


@app.command()
def version_command() -> None:
    """Print the installed package version."""
    typer.echo(f"youtrack-aitrack {_package_version()}")


app.command("init")(init_command)
app.command("run")(run_command)
app.command("poll")(poll_command)
app.command("version")(version_command)
app.add_typer(workflows_app, name="workflows")


if __name__ == "__main__":
    app()
