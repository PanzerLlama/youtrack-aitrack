"""Tests for Context."""

from datetime import UTC, datetime

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


def test_context_frozen() -> None:
    c = Context(issue=_event())
    with pytest.raises(ValidationError):
        c.branch = "renamed"
