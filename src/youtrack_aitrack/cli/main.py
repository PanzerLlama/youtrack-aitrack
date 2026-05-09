"""CLI entry point for youtrack-aitrack."""
from __future__ import annotations

import typer

app = typer.Typer(
    name="youtrack-aitrack",
    help="YAML-driven workflow engine for YouTrack AI-agent automations.",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """YAML-driven workflow engine for YouTrack AI-agent automations."""


@app.command()
def version() -> None:
    """Print the installed package version."""
    typer.echo("youtrack-aitrack 0.1.0a0")


if __name__ == "__main__":
    app()
