"""CLI entry point for youtrack-aitrack."""

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv

from youtrack_aitrack.cli.config_dir import resolve_config_dir
from youtrack_aitrack.cli.init import init_command

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


@app.callback()
def _root(
    ctx: typer.Context,
    config_dir: Path | None = _CONFIG_DIR_OPTION,
) -> None:
    """YAML-driven workflow engine for YouTrack AI-agent automations."""
    resolved = resolve_config_dir(config_dir)
    env_file = resolved / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = resolved


@app.command()
def version() -> None:
    """Print the installed package version."""
    typer.echo("youtrack-aitrack 0.1.0a0")


app.command("init")(init_command)


if __name__ == "__main__":
    app()
