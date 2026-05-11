"""Tests for the GitDiffProvider Protocol and its NoOp default."""

from __future__ import annotations

from pathlib import Path

from youtrack_aitrack.domain.inputs import GitDiffProvider, _NoOpGitDiffProvider


class _FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def resolve_branch(self, task_id: str, *, repo_dir: Path, pattern: str) -> str | None:
        self.calls.append(("resolve", task_id, str(repo_dir), pattern))
        return f"{task_id}-feature"

    def diff(self, repo_dir: Path, branch: str, base: str = "main") -> str:
        self.calls.append(("diff", str(repo_dir), branch, base))
        return "diff-body"


def _accepts_provider(p: GitDiffProvider) -> GitDiffProvider:
    return p


def test_fake_satisfies_protocol() -> None:
    fake = _FakeProvider()
    accepted = _accepts_provider(fake)
    assert accepted is fake


def test_noop_satisfies_protocol() -> None:
    noop = _NoOpGitDiffProvider()
    accepted = _accepts_provider(noop)
    assert accepted is noop


def test_noop_returns_sensible_defaults(tmp_path: Path) -> None:
    noop = _NoOpGitDiffProvider()
    assert noop.resolve_branch("ABC-1", repo_dir=tmp_path, pattern="{task_id}-*") is None
    assert noop.diff(tmp_path, "any-branch") == ""
    assert noop.diff(tmp_path, "any-branch", base="develop") == ""


def test_fake_forwards_args(tmp_path: Path) -> None:
    fake = _FakeProvider()
    branch = fake.resolve_branch("XYZ-7", repo_dir=tmp_path, pattern="{task_id}-*")
    assert branch == "XYZ-7-feature"
    out = fake.diff(tmp_path, "main", base="develop")
    assert out == "diff-body"
    assert fake.calls == [
        ("resolve", "XYZ-7", str(tmp_path), "{task_id}-*"),
        ("diff", str(tmp_path), "main", "develop"),
    ]
