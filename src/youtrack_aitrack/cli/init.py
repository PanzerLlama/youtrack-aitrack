"""``youtrack-aitrack init`` — scaffold the per-instance config directory."""

from __future__ import annotations

from pathlib import Path

import typer

CONFIG_YAML_TEMPLATE = """\
# youtrack-aitrack instance config.
#
# ${VAR} references resolve from environment variables. The CLI auto-loads
# <config-dir>/.env (via python-dotenv) before any subcommand runs, so you
# can keep secrets out of this file by populating .env instead.

youtrack:
  url: ${YOUTRACK_URL}
  token: ${YOUTRACK_TOKEN}
  project: ${YOUTRACK_PROJECT}

anthropic:
  api_key: ${ANTHROPIC_API_KEY}           # only needed when cli_agent_mode is 'bare'

paths:
  workflows_dir: workflows
  prompts_dir: prompts
  runs_dir: runs

defaults:
  branch_pattern: "{task_id}-*"
  poll_interval_seconds: 60
  poll_lookback_seconds: 3600              # first-poll window (1h); subsequent polls use cursor
  git_base_branch: main                    # base for 'git diff --merge-base <base> <branch>'
  default_agent: claude_code_cli           # AgentRunner backend; only one ships today
  cli_agent_mode: oauth                    # 'oauth' uses `claude login`; 'bare' needs the API key
  # base_url: https://staging.example.com   # optional; enables clickable URLs in pages_changed
  # include_tags: [daemon-test, backend]    # optional; empty/absent = process all issues
"""

ENV_EXAMPLE_TEMPLATE = """\
# Copy to .env and fill in. The CLI auto-loads <config-dir>/.env at startup.
YOUTRACK_URL=
YOUTRACK_TOKEN=
YOUTRACK_PROJECT=
ANTHROPIC_API_KEY=
"""

_FILE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("config.yaml", CONFIG_YAML_TEMPLATE),
    (".env.example", ENV_EXAMPLE_TEMPLATE),
)
_SUBDIRS: tuple[str, ...] = ("workflows", "prompts", "runs")


def scaffold(config_dir: Path, *, force: bool = False) -> list[Path]:
    """Create config_dir layout. Idempotent unless *force* is true.

    Returns the list of paths that were written or created on this call.
    """
    written: list[Path] = []
    config_dir.mkdir(parents=True, exist_ok=True)
    for name, content in _FILE_TEMPLATES:
        target = config_dir / name
        if target.exists() and not force:
            continue
        target.write_text(content)
        written.append(target)
    for sub in _SUBDIRS:
        sub_path = config_dir / sub
        sub_path.mkdir(exist_ok=True)
        gitkeep = sub_path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("")
            written.append(gitkeep)
    return written


def init_command(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Overwrite existing template files."),
) -> None:
    """Scaffold the per-instance config directory with templates and empty subdirs."""
    config_dir: Path = ctx.obj["config_dir"]
    written = scaffold(config_dir, force=force)
    if written:
        typer.echo(f"Initialized {config_dir}:")
        for p in written:
            typer.echo(f"  + {p.relative_to(config_dir)}")
    else:
        typer.echo(f"{config_dir} already initialized (no changes); use --force to overwrite.")
