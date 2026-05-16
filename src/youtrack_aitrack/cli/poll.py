"""``youtrack-aitrack poll`` — one-shot or daemon-mode polling loop."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from pathlib import Path

import typer

from youtrack_aitrack.config import InstanceConfigError, load_instance_config
from youtrack_aitrack.runtime import Poller, PollResult, build_poller

_DAEMON_OPTION = typer.Option(False, "--daemon", help="Loop forever, sleeping between polls.")
_REPO_DIR_OPTION = typer.Option(
    None, "--repo-dir", help="Git repo root (default: current working directory)."
)
_INTERVAL_OPTION = typer.Option(
    None,
    "--interval-seconds",
    help="Override poll interval (default: config.defaults.poll_interval_seconds).",
)
_MAX_ITER_OPTION = typer.Option(
    None,
    "--max-iterations",
    help="Daemon-only: exit after N iterations. For testing; omit for true daemon.",
    hidden=True,
)
_DRY_RUN_OPTION = typer.Option(
    False, "--dry-run", help="Dispatch as normal but skip YouTrack field writes and comments."
)
_STUB_LLM_OPTION = typer.Option(
    False,
    "--stub-llm",
    help="Substitute a placeholder for every Anthropic call (zero LLM cost).",
)


def poll_command(
    ctx: typer.Context,
    daemon: bool = _DAEMON_OPTION,
    repo_dir: Path | None = _REPO_DIR_OPTION,
    interval_seconds: float | None = _INTERVAL_OPTION,
    max_iterations: int | None = _MAX_ITER_OPTION,
    dry_run: bool = _DRY_RUN_OPTION,
    stub_llm: bool = _STUB_LLM_OPTION,
) -> None:
    """Poll YouTrack activity feed and dispatch matching workflows."""
    config_dir: Path = ctx.obj["config_dir"]
    config_yaml = config_dir / "config.yaml"
    if not config_yaml.is_file():
        raise typer.BadParameter(f"no config.yaml at {config_yaml}; run 'init' first.")
    try:
        config = load_instance_config(config_yaml)
    except InstanceConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc

    poller = build_poller(config, config_dir, repo_dir=repo_dir, dry_run=dry_run, stub_llm=stub_llm)
    if not daemon:
        result = asyncio.run(poller.poll_once())
        _print_result(result)
        return
    interval = (
        interval_seconds
        if interval_seconds is not None
        else float(config.defaults.poll_interval_seconds)
    )
    asyncio.run(_run_daemon(poller, interval=interval, max_iterations=max_iterations))


async def _run_daemon(poller: Poller, *, interval: float, max_iterations: int | None) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    handlers_installed: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
            handlers_installed.append(sig)
    try:
        await poller.poll_loop(
            interval_seconds=interval,
            stop=stop,
            on_iteration=_print_result,
            max_iterations=max_iterations,
        )
    finally:
        for sig in handlers_installed:
            with contextlib.suppress(NotImplementedError):
                loop.remove_signal_handler(sig)


def _print_result(result: PollResult) -> None:
    fired = sum(len(r.action_results) for r in result.reports)
    typer.echo(
        f"poll: cursor {result.cursor_before!r} -> {result.cursor_after!r} "
        f"events={result.event_count} filtered={result.events_filtered} "
        f"workflows_fired={len(result.reports)} actions_run={fired}"
    )
