"""BeadsCliClient — create issues in the target repo's beads (bd) database.

Implements the IssueTrackerClient Protocol owned by the ``bd_issue`` action.
Beads is optional tooling: availability means the ``bd`` binary is on PATH
*and* the repo carries a ``.beads/`` workspace. The issue body travels over
stdin (``--body-file -``) so long plans never hit argv limits.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from youtrack_aitrack.domain.actions.bd_issue import TrackedIssue

_TIMEOUT_SECONDS = 60


class BeadsError(RuntimeError):
    """Raised when ``bd create`` fails, times out, or returns no issue id."""


class BeadsCliClient:
    def __init__(self, *, binary: str = "bd") -> None:
        self._binary = binary

    def is_available(self, repo_dir: Path) -> bool:
        return shutil.which(self._binary) is not None and (repo_dir / ".beads").is_dir()

    def create_issue(self, repo_dir: Path, issue: TrackedIssue) -> str:
        args = [
            self._binary,
            "create",
            "--silent",
            "--title",
            issue.title,
            "--type",
            issue.issue_type,
            "--priority",
            str(issue.priority),
            "--body-file",
            "-",
        ]
        if issue.external_ref:
            args.extend(["--external-ref", issue.external_ref])
        stdout = self._run(args, repo_dir, stdin=issue.body)
        issue_id = stdout.strip().splitlines()[-1].strip() if stdout.strip() else ""
        if not issue_id:
            raise BeadsError("bd create returned no issue id")
        return issue_id

    def _run(self, args: list[str], repo_dir: Path, *, stdin: str) -> str:
        try:
            proc = subprocess.run(
                args,
                cwd=repo_dir,
                input=stdin,
                check=True,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            raise BeadsError(f"bd {args[1]} failed: {stderr}") from exc
        except subprocess.TimeoutExpired as exc:
            raise BeadsError(f"bd {args[1]} timed out") from exc
        except FileNotFoundError as exc:
            raise BeadsError(f"bd executable not found: {self._binary}") from exc
        return proc.stdout
