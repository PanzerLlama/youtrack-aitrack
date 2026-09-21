"""run_git — one guarded subprocess entry point shared by the git adapters."""

from __future__ import annotations

import subprocess
from pathlib import Path

_TIMEOUT_SECONDS = 30


class GitCommandError(RuntimeError):
    """Raised when a git subprocess fails, times out, or the executable is missing."""


def run_git(
    args: list[str], repo_dir: Path, *, git_executable: str = "git"
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [git_executable, *args],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        raise GitCommandError(f"git {' '.join(args)} failed: {stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitCommandError(f"git {' '.join(args)} timed out") from exc
    except FileNotFoundError as exc:
        raise GitCommandError(f"git executable not found: {git_executable}") from exc
