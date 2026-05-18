"""Tests for Context."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.run import ActionResult


def _event() -> IssueEvent:
    return IssueEvent(
        issue_id="DEMO-1",
        project="DEMO",
        event_kind="manual",
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
    )


def test_context_minimal() -> None:
    c = Context(issue=_event())
    assert c.branch is None
    assert c.commit_sha is None
    assert c.repo_path is None
    assert c.action_outputs == {}


def test_context_with_outputs() -> None:
    c = Context(
        issue=_event(),
        branch="DEMO-1-fix-foo",
        diff="--- a\n+++ b\n",
        action_outputs={"a1": ActionResult(action_id="a1", success=True)},
    )
    assert c.branch == "DEMO-1-fix-foo"
    assert "a1" in c.action_outputs


def test_context_with_commit_sha_and_repo_path() -> None:
    c = Context(
        issue=_event(),
        commit_sha="deadbeef",
        repo_path=Path("/tmp/repo"),
    )
    assert c.commit_sha == "deadbeef"
    assert c.repo_path == Path("/tmp/repo")


def test_context_frozen() -> None:
    c = Context(issue=_event())
    with pytest.raises(ValidationError):
        c.branch = "renamed"
