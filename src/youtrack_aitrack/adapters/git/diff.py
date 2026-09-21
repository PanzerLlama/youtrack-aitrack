"""GitDiffAdapter — branch resolution and diff extraction via the git CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

from youtrack_aitrack.adapters.git.process import GitCommandError, run_git


class GitDiffError(GitCommandError):
    """Raised when the git subprocess fails or branch resolution is ambiguous."""


class GitDiffAdapter:
    def __init__(self, *, git_executable: str = "git") -> None:
        self._git = git_executable

    def resolve_branch(self, task_id: str, *, repo_dir: Path, pattern: str) -> str | None:
        glob = pattern.replace("{task_id}", task_id)
        # --end-of-options stops git from treating an argument starting with '-' as a flag,
        # regardless of arg position. Hardening against task_id values like '--help'.
        result = self._run(["branch", "--list", "--all", "--end-of-options", glob], repo_dir)
        names = _parse_branch_list(result.stdout)
        if not names:
            return None
        if len(names) > 1:
            raise GitDiffError(
                f"ambiguous branch match for task_id={task_id!r} pattern={pattern!r}: {names}"
            )
        return names[0]

    def diff(self, repo_dir: Path, branch: str, base: str = "main") -> str:
        result = self._run(["diff", "--merge-base", "--end-of-options", base, branch], repo_dir)
        return result.stdout

    def commit_sha(self, repo_dir: Path, branch: str) -> str:
        # --verify makes rev-parse output only the resolved SHA (without it,
        # rev-parse echoes every positional arg, including --end-of-options).
        result = self._run(["rev-parse", "--verify", "--end-of-options", branch], repo_dir)
        return result.stdout.strip()

    def _run(self, args: list[str], repo_dir: Path) -> subprocess.CompletedProcess[str]:
        try:
            return run_git(args, repo_dir, git_executable=self._git)
        except GitCommandError as exc:
            raise GitDiffError(str(exc)) from exc


def _parse_branch_list(stdout: str) -> list[str]:
    seen: set[str] = set()
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or " -> " in line:
            continue
        if line.startswith("* "):
            line = line[2:].strip()
        if line.startswith("remotes/"):
            parts = line.split("/", 2)
            if len(parts) == 3:
                line = parts[2]
        seen.add(line)
    return sorted(seen)
