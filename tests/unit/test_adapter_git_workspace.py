"""Tests for GitWorkspaceAdapter (real local git repos in tmp_path)."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

import pytest

from youtrack_aitrack.adapters.git.process import GitCommandError
from youtrack_aitrack.adapters.git.workspace import GitWorkspaceAdapter
from youtrack_aitrack.domain.actions.git_branch import BranchCreator
from youtrack_aitrack.domain.actions.write_file import RepoFileWriter


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "README").write_text("init\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)


def _accepts_creator(c: BranchCreator) -> BranchCreator:
    return c


def _accepts_writer(w: RepoFileWriter) -> RepoFileWriter:
    return w


def test_adapter_satisfies_both_protocols() -> None:
    adapter = GitWorkspaceAdapter()
    assert _accepts_creator(adapter) is adapter
    assert _accepts_writer(adapter) is adapter


def test_current_branch_and_has_branch(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    adapter = GitWorkspaceAdapter()
    assert adapter.current_branch(tmp_path) == "main"
    assert adapter.has_branch(tmp_path, "main") is True
    assert adapter.has_branch(tmp_path, "PROJ-1-nope") is False


def test_create_branch_from_base_then_switch(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    adapter = GitWorkspaceAdapter()

    adapter.create_branch(tmp_path, "PROJ-1-add-export", base="main")
    assert adapter.has_branch(tmp_path, "PROJ-1-add-export") is True
    assert adapter.current_branch(tmp_path) == "main"

    adapter.switch(tmp_path, "PROJ-1-add-export")
    assert adapter.current_branch(tmp_path) == "PROJ-1-add-export"
    branch_sha = _git(["rev-parse", "PROJ-1-add-export"], tmp_path)
    assert branch_sha == _git(["rev-parse", "main"], tmp_path)


def test_create_branch_with_unknown_base_raises(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    with pytest.raises(GitCommandError, match="failed"):
        GitWorkspaceAdapter().create_branch(tmp_path, "PROJ-1-x", base="does-not-exist")


def test_is_clean_ignores_untracked_but_not_tracked_edits(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    adapter = GitWorkspaceAdapter()
    assert adapter.is_clean(tmp_path) is True

    (tmp_path / "scratch.txt").write_text("untracked\n")
    assert adapter.is_clean(tmp_path) is True

    (tmp_path / "README").write_text("edited\n")
    assert adapter.is_clean(tmp_path) is False


def test_write_text_creates_parent_dirs(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    GitWorkspaceAdapter().write_text(tmp_path, PurePosixPath("docs/plans/PROJ-1.md"), "# Plan\n")
    assert (tmp_path / "docs" / "plans" / "PROJ-1.md").read_text() == "# Plan\n"


def test_commit_paths_commits_only_named_files_and_returns_sha(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    adapter = GitWorkspaceAdapter()
    rel = PurePosixPath("docs/plans/PROJ-1.md")
    adapter.write_text(tmp_path, rel, "# Plan\n")
    (tmp_path / "README").write_text("unrelated edit\n")

    sha = adapter.commit_paths(tmp_path, [rel], "docs: plan for PROJ-1")

    assert sha == _git(["rev-parse", "HEAD"], tmp_path)
    assert len(sha) == 40
    assert _git(["log", "-1", "--pretty=%s"], tmp_path) == "docs: plan for PROJ-1"
    assert _git(["show", "--stat", "--pretty=", "HEAD"], tmp_path).count("|") == 1
    assert adapter.is_clean(tmp_path) is False  # README edit stayed uncommitted


def test_branch_name_starting_with_dash_is_not_a_flag(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    adapter = GitWorkspaceAdapter()
    with pytest.raises(GitCommandError):
        adapter.create_branch(tmp_path, "--help", base="main")
