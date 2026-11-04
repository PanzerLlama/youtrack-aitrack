"""Dry-run adapters — satisfy the write-side Protocols while touching nothing."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from youtrack_aitrack.domain.actions.bd_issue import IssueTrackerClient, TrackedIssue
from youtrack_aitrack.domain.actions.git_branch import BranchCreator


class NoOpFieldWriter:
    """Dry-run FieldWriter — accepts calls, performs no I/O."""

    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None:
        return None


class NoOpCommentPoster:
    """Dry-run CommentPoster — accepts calls, performs no I/O."""

    async def post_comment(self, issue_id: str, body: str) -> None:
        return None


class NoOpBranchCreator:
    """Dry-run BranchCreator — reports a clean tree and creates nothing."""

    def current_branch(self, repo_dir: Path) -> str | None:
        return None

    def has_branch(self, repo_dir: Path, name: str) -> bool:
        return False

    def is_clean(self, repo_dir: Path) -> bool:
        return True

    def create_branch(self, repo_dir: Path, name: str, *, base: str) -> None:
        return None

    def switch(self, repo_dir: Path, name: str) -> None:
        return None


class DryRunBranchCreator:
    """Dry-run BranchCreator — reads the real repo state, creates and switches nothing.

    Real reads let the action predict accurately: 'would reuse X' when X exists,
    and the dirty-tree refusal fires exactly as it would on a real run.
    """

    def __init__(self, real: BranchCreator) -> None:
        self._real = real

    def current_branch(self, repo_dir: Path) -> str | None:
        return self._real.current_branch(repo_dir)

    def has_branch(self, repo_dir: Path, name: str) -> bool:
        return self._real.has_branch(repo_dir, name)

    def is_clean(self, repo_dir: Path) -> bool:
        return self._real.is_clean(repo_dir)

    def create_branch(self, repo_dir: Path, name: str, *, base: str) -> None:
        return None

    def switch(self, repo_dir: Path, name: str) -> None:
        return None


class NoOpRepoFileWriter:
    """Dry-run RepoFileWriter — accepts writes and commits, touches nothing."""

    def write_text(self, repo_dir: Path, relative_path: PurePosixPath, text: str) -> None:
        return None

    def commit_paths(self, repo_dir: Path, paths: list[PurePosixPath], message: str) -> str:
        return ""


class DryRunIssueTracker:
    """Dry-run IssueTrackerClient — reports real availability, never creates anything."""

    def __init__(self, real: IssueTrackerClient) -> None:
        self._real = real

    def is_available(self, repo_dir: Path) -> bool:
        return self._real.is_available(repo_dir)

    def create_issue(self, repo_dir: Path, issue: TrackedIssue) -> str:
        return "dry-run"
