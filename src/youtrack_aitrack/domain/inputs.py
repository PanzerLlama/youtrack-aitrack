"""Protocols for workflow input providers (git diff, route index, etc.)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class GitDiffProvider(Protocol):
    def resolve_branch(self, task_id: str, *, repo_dir: Path, pattern: str) -> str | None: ...

    def diff(self, repo_dir: Path, branch: str, base: str = "main") -> str: ...


class _NoOpGitDiffProvider:
    def resolve_branch(self, task_id: str, *, repo_dir: Path, pattern: str) -> str | None:
        return None

    def diff(self, repo_dir: Path, branch: str, base: str = "main") -> str:
        return ""
