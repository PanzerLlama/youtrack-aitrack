"""Tests for GitBranchAction against a recording BranchCreator fake."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import youtrack_aitrack.domain.actions  # noqa: F401
from youtrack_aitrack.domain.actions.git_branch import BranchCreator, GitBranchAction
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.issue import IssueDetails
from youtrack_aitrack.registry import action_registry


class _FakeGit:
    def __init__(
        self,
        *,
        current: str | None = "main",
        branches: set[str] | None = None,
        clean: bool = True,
    ) -> None:
        self.current = current
        self.branches = branches if branches is not None else {"main"}
        self.clean = clean
        self.created: list[tuple[str, str]] = []
        self.switched: list[str] = []

    def current_branch(self, repo_dir: Path) -> str | None:
        return self.current

    def has_branch(self, repo_dir: Path, name: str) -> bool:
        return name in self.branches

    def is_clean(self, repo_dir: Path) -> bool:
        return self.clean

    def create_branch(self, repo_dir: Path, name: str, *, base: str) -> None:
        self.created.append((name, base))
        self.branches.add(name)

    def switch(self, repo_dir: Path, name: str) -> None:
        self.switched.append(name)
        self.current = name


def _accepts(creator: BranchCreator) -> BranchCreator:
    return creator


def _ctx(summary: str | None = "Add CSV export") -> Context:
    event = IssueEvent(
        issue_id="PROJ-12",
        project="PROJ",
        event_kind="manual",
        timestamp=datetime(2026, 9, 21, tzinfo=UTC),
    )
    details = IssueDetails(summary=summary) if summary is not None else None
    return Context(issue=event, issue_details=details, repo_path=Path("/repo"))


def test_registered() -> None:
    assert action_registry.get("git_branch") is GitBranchAction


def test_fake_satisfies_protocol() -> None:
    git = _FakeGit()
    assert _accepts(git) is git


@pytest.mark.asyncio
async def test_creates_branch_from_base_and_switches() -> None:
    git = _FakeGit()
    action = GitBranchAction(id="b", base="develop", git=git)

    result = await action.execute(_ctx())

    assert result.success is True
    assert git.created == [("PROJ-12-add-csv-export", "develop")]
    assert git.switched == ["PROJ-12-add-csv-export"]
    assert result.output is not None
    assert result.output["branch"] == "PROJ-12-add-csv-export"
    assert result.output["created"] is True
    assert "created PROJ-12-add-csv-export from develop" in result.output["note"]


@pytest.mark.asyncio
async def test_existing_branch_is_reused_not_recreated() -> None:
    git = _FakeGit(branches={"main", "PROJ-12-add-csv-export"})
    action = GitBranchAction(id="b", git=git)

    result = await action.execute(_ctx())

    assert result.success is True
    assert git.created == []
    assert git.switched == ["PROJ-12-add-csv-export"]
    assert result.output is not None
    assert result.output["created"] is False


@pytest.mark.asyncio
async def test_dirty_tree_blocks_switch() -> None:
    git = _FakeGit(clean=False)
    action = GitBranchAction(id="b", git=git)

    result = await action.execute(_ctx())

    assert result.success is False
    assert result.error is not None
    assert "uncommitted changes" in result.error
    assert git.created == []
    assert git.switched == []


@pytest.mark.asyncio
async def test_dirty_tree_is_fine_when_already_on_target_branch() -> None:
    git = _FakeGit(
        current="PROJ-12-add-csv-export",
        branches={"main", "PROJ-12-add-csv-export"},
        clean=False,
    )
    action = GitBranchAction(id="b", git=git)

    result = await action.execute(_ctx())

    assert result.success is True


@pytest.mark.asyncio
async def test_checkout_false_creates_without_switching() -> None:
    git = _FakeGit()
    action = GitBranchAction(id="b", checkout=False, git=git)

    result = await action.execute(_ctx())

    assert result.success is True
    assert git.created == [("PROJ-12-add-csv-export", "main")]
    assert git.switched == []


@pytest.mark.asyncio
async def test_missing_summary_fails_when_template_needs_slug() -> None:
    git = _FakeGit()
    action = GitBranchAction(id="b", git=git)

    result = await action.execute(_ctx(summary=None))

    assert result.success is False
    assert result.error is not None
    assert "empty slug" in result.error
    assert git.created == []


@pytest.mark.asyncio
async def test_custom_template_without_slug_works_without_details() -> None:
    git = _FakeGit()
    action = GitBranchAction(id="b", name="feature/{task_id}", git=git)

    result = await action.execute(_ctx(summary=None))

    assert result.success is True
    assert git.created == [("feature/PROJ-12", "main")]


@pytest.mark.asyncio
async def test_default_noop_creator_succeeds_without_io() -> None:
    result = await GitBranchAction(id="b").execute(_ctx())
    assert result.success is True
