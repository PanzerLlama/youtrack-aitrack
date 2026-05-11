"""Tests for GitDiffAdapter (real local git repos in tmp_path)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from youtrack_aitrack.adapters.git.diff import GitDiffAdapter, GitDiffError
from youtrack_aitrack.domain.inputs import GitDiffProvider


def _accepts_provider(p: GitDiffProvider) -> GitDiffProvider:
    return p


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "README").write_text("init\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)


def _make_branch(repo: Path, branch: str, file: str, content: str) -> None:
    _git(["checkout", "-b", branch], repo)
    (repo / file).write_text(content)
    _git(["add", file], repo)
    _git(["commit", "-m", f"add {file}"], repo)
    _git(["checkout", "main"], repo)


def test_adapter_satisfies_protocol() -> None:
    adapter = GitDiffAdapter()
    accepted = _accepts_provider(adapter)
    assert accepted is adapter


def test_resolve_branch_single_match(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _make_branch(tmp_path, "TASK-1-feature", "a.txt", "hello\n")
    adapter = GitDiffAdapter()
    assert (
        adapter.resolve_branch("TASK-1", repo_dir=tmp_path, pattern="{task_id}-*")
        == "TASK-1-feature"
    )


def test_resolve_branch_no_match_returns_none(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    adapter = GitDiffAdapter()
    assert adapter.resolve_branch("ZZZ-9", repo_dir=tmp_path, pattern="{task_id}-*") is None


def test_resolve_branch_ambiguous_raises(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _make_branch(tmp_path, "TASK-1-one", "a.txt", "a\n")
    _make_branch(tmp_path, "TASK-1-two", "b.txt", "b\n")
    adapter = GitDiffAdapter()
    with pytest.raises(GitDiffError, match="ambiguous"):
        adapter.resolve_branch("TASK-1", repo_dir=tmp_path, pattern="{task_id}-*")


def test_resolve_branch_pattern_without_placeholder(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _make_branch(tmp_path, "feature-x", "a.txt", "hello\n")
    adapter = GitDiffAdapter()
    assert adapter.resolve_branch("ignored", repo_dir=tmp_path, pattern="feature-*") == "feature-x"


def test_diff_returns_branch_changes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _make_branch(tmp_path, "feat", "new.txt", "added line\n")
    adapter = GitDiffAdapter()
    out = adapter.diff(tmp_path, "feat", base="main")
    assert "new.txt" in out
    assert "added line" in out


def test_diff_empty_when_branch_matches_base(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _git(["branch", "twin"], tmp_path)
    adapter = GitDiffAdapter()
    assert adapter.diff(tmp_path, "twin", base="main") == ""


def test_diff_with_unknown_branch_raises(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    adapter = GitDiffAdapter()
    with pytest.raises(GitDiffError, match="git diff"):
        adapter.diff(tmp_path, "nope-not-a-branch", base="main")


def test_git_executable_not_found_raises() -> None:
    adapter = GitDiffAdapter(git_executable="/no/such/git-binary-xyz")
    with pytest.raises(GitDiffError, match="git executable not found"):
        adapter.resolve_branch("X", repo_dir=Path("/tmp"), pattern="x")


def test_resolve_branch_dedupes_local_and_remote(tmp_path: Path) -> None:
    """Same logical branch appearing locally and as a 'remote' ref should count once."""
    _init_repo(tmp_path)
    _make_branch(tmp_path, "ABC-1-feat", "a.txt", "hi\n")
    _git(
        [
            "update-ref",
            "refs/remotes/origin/ABC-1-feat",
            "ABC-1-feat",
        ],
        tmp_path,
    )
    adapter = GitDiffAdapter()
    assert adapter.resolve_branch("ABC-1", repo_dir=tmp_path, pattern="{task_id}-*") == "ABC-1-feat"
