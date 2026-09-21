"""GitWorkspaceAdapter — write-side git operations: branches, files, commits.

Implements the BranchCreator and RepoFileWriter Protocols owned by the domain
actions ``git_branch`` and ``write_file``. Every ref argument is preceded by
``--end-of-options`` (or ``--``) so issue-derived names can never be parsed as
flags.
"""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

from youtrack_aitrack.adapters.git.process import GitCommandError, run_git


class GitWorkspaceAdapter:
    def __init__(self, *, git_executable: str = "git") -> None:
        self._git = git_executable

    def current_branch(self, repo_dir: Path) -> str | None:
        name = self._run(["branch", "--show-current"], repo_dir).stdout.strip()
        return name or None

    def has_branch(self, repo_dir: Path, name: str) -> bool:
        try:
            self._run(["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], repo_dir)
        except GitCommandError:
            return False
        return True

    def is_clean(self, repo_dir: Path) -> bool:
        # Untracked files never block a switch; only tracked modifications do.
        out = self._run(["status", "--porcelain", "--untracked-files=no"], repo_dir).stdout
        return out.strip() == ""

    def create_branch(self, repo_dir: Path, name: str, *, base: str) -> None:
        self._run(["branch", "--end-of-options", name, base], repo_dir)

    def switch(self, repo_dir: Path, name: str) -> None:
        self._run(["switch", "--end-of-options", name], repo_dir)

    def write_text(self, repo_dir: Path, relative_path: PurePosixPath, text: str) -> None:
        target = repo_dir / Path(*relative_path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def commit_paths(self, repo_dir: Path, paths: list[PurePosixPath], message: str) -> str:
        rel = [str(p) for p in paths]
        self._run(["add", "--", *rel], repo_dir)
        self._run(["commit", "--quiet", "-m", message, "--", *rel], repo_dir)
        return self._run(["rev-parse", "HEAD"], repo_dir).stdout.strip()

    def _run(self, args: list[str], repo_dir: Path) -> subprocess.CompletedProcess[str]:
        return run_git(args, repo_dir, git_executable=self._git)
