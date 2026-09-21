"""Tests for BdIssueAction against recording tracker / file-writer fakes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

import youtrack_aitrack.domain.actions  # noqa: F401
from youtrack_aitrack.domain.actions.bd_issue import (
    BdIssueAction,
    IssueTrackerClient,
    TrackedIssue,
)
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.issue import IssueDetails
from youtrack_aitrack.domain.run import ActionResult
from youtrack_aitrack.registry import action_registry


class _FakeTracker:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.created: list[tuple[Path, TrackedIssue]] = []

    def is_available(self, repo_dir: Path) -> bool:
        return self.available

    def create_issue(self, repo_dir: Path, issue: TrackedIssue) -> str:
        self.created.append((repo_dir, issue))
        return "proj-a1b2"


class _FakeWriter:
    def __init__(self) -> None:
        self.written: list[tuple[Path, PurePosixPath, str]] = []
        self.commits: list[tuple[Path, list[PurePosixPath], str]] = []

    def write_text(self, repo_dir: Path, relative_path: PurePosixPath, text: str) -> None:
        self.written.append((repo_dir, relative_path, text))

    def commit_paths(self, repo_dir: Path, paths: list[PurePosixPath], message: str) -> str:
        self.commits.append((repo_dir, paths, message))
        return "abcdef1234567890"


def _accepts(t: IssueTrackerClient) -> IssueTrackerClient:
    return t


def _ctx(*, summary: str | None = "Add CSV export", with_text: bool = True) -> Context:
    event = IssueEvent(
        issue_id="PROJ-12",
        project="PROJ",
        event_kind="manual",
        timestamp=datetime(2026, 9, 21, tzinfo=UTC),
    )
    output = {"text": "**Understanding**\nPlan body\n"} if with_text else {"fields": {}}
    return Context(
        issue=event,
        issue_details=IssueDetails(summary=summary) if summary is not None else None,
        repo_path=Path("/repo"),
        action_outputs={"plan": ActionResult(action_id="plan", success=True, output=output)},
    )


def test_registered_and_fake_satisfies_protocol() -> None:
    assert action_registry.get("bd_issue") is BdIssueAction
    t = _FakeTracker()
    assert _accepts(t) is t


@pytest.mark.asyncio
async def test_creates_beads_issue_with_plan_as_body_and_external_ref() -> None:
    tracker = _FakeTracker()
    action = BdIssueAction(id="track", source="plan", issue_type="feature", tracker=tracker)

    result = await action.execute(_ctx())

    assert result.success is True and result.skipped is False
    [(repo, issue)] = tracker.created
    assert repo == Path("/repo")
    assert issue.title == "PROJ-12: Add CSV export"
    assert issue.body == "**Understanding**\nPlan body\n"
    assert issue.issue_type == "feature"
    assert issue.priority == 2
    assert issue.external_ref == "PROJ-12"
    assert result.output is not None
    assert result.output["tracker"] == "beads"
    assert result.output["issue_id"] == "proj-a1b2"
    assert result.output["note"] == "created beads issue proj-a1b2"
    assert "proj-a1b2" in result.output["text"]


@pytest.mark.asyncio
async def test_title_without_summary_is_trimmed() -> None:
    tracker = _FakeTracker()
    action = BdIssueAction(id="track", source="plan", tracker=tracker)

    await action.execute(_ctx(summary=None))

    assert tracker.created[0][1].title == "PROJ-12"


@pytest.mark.asyncio
async def test_falls_back_to_file_when_beads_unavailable() -> None:
    tracker = _FakeTracker(available=False)
    writer = _FakeWriter()
    action = BdIssueAction(
        id="track",
        source="plan",
        fallback_path="docs/plans/{task_id}.md",
        fallback_commit_message="docs: plan for {task_id}",
        tracker=tracker,
        writer=writer,
    )

    result = await action.execute(_ctx())

    assert result.success is True and result.skipped is False
    assert tracker.created == []
    assert writer.written == [
        (Path("/repo"), PurePosixPath("docs/plans/PROJ-12.md"), "**Understanding**\nPlan body\n")
    ]
    assert writer.commits == [
        (Path("/repo"), [PurePosixPath("docs/plans/PROJ-12.md")], "docs: plan for PROJ-12")
    ]
    assert result.output is not None
    assert result.output["tracker"] == "file"
    assert result.output["path"] == "docs/plans/PROJ-12.md"
    assert (
        result.output["note"]
        == "beads unavailable; wrote docs/plans/PROJ-12.md; committed abcdef1234"
    )


@pytest.mark.asyncio
async def test_fallback_without_commit_message_only_writes() -> None:
    writer = _FakeWriter()
    action = BdIssueAction(
        id="track",
        source="plan",
        fallback_path="PLAN.md",
        tracker=_FakeTracker(available=False),
        writer=writer,
    )

    result = await action.execute(_ctx())

    assert writer.commits == []
    assert result.output is not None
    assert result.output["committed_sha"] is None


@pytest.mark.asyncio
async def test_skips_when_beads_unavailable_and_no_fallback() -> None:
    action = BdIssueAction(id="track", source="plan", tracker=_FakeTracker(available=False))

    result = await action.execute(_ctx())

    assert result.success is True
    assert result.skipped is True
    assert result.skip_reason is not None
    assert "beads unavailable" in result.skip_reason


@pytest.mark.asyncio
async def test_fallback_path_escaping_repo_fails() -> None:
    action = BdIssueAction(
        id="track", source="plan", fallback_path="../x.md", tracker=_FakeTracker(available=False)
    )
    result = await action.execute(_ctx())
    assert result.success is False
    assert result.error is not None
    assert "inside the repo" in result.error


@pytest.mark.asyncio
async def test_fails_when_source_has_no_text() -> None:
    tracker = _FakeTracker()
    action = BdIssueAction(id="track", source="plan", tracker=tracker)

    result = await action.execute(_ctx(with_text=False))

    assert result.success is False
    assert tracker.created == []


@pytest.mark.asyncio
async def test_default_noop_tracker_skips() -> None:
    result = await BdIssueAction(id="track", source="plan").execute(_ctx())
    assert result.skipped is True
