"""Tests for IssueEvent."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from youtrack_aitrack.domain.event import IssueEvent


def test_issue_event_status_change() -> None:
    e = IssueEvent(
        issue_id="DEMO-2527",
        project="DEMO",
        event_kind="status_change",
        from_state="In Progress",
        to_state="Ready for testing",
        timestamp=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
    )
    assert e.event_kind == "status_change"
    assert e.to_state == "Ready for testing"


def test_issue_event_manual() -> None:
    e = IssueEvent(
        issue_id="DEMO-2527",
        project="DEMO",
        event_kind="manual",
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
    )
    assert e.from_state is None
    assert e.to_state is None


def test_issue_event_invalid_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        IssueEvent(
            issue_id="DEMO-1",
            project="DEMO",
            event_kind="bogus",
            timestamp=datetime(2026, 5, 9, tzinfo=UTC),
        )


def test_issue_event_field_change() -> None:
    e = IssueEvent(
        issue_id="DEMO-2527",
        project="DEMO",
        event_kind="field_change",
        field_name="State",
        from_value="Open",
        to_value="Ready for testing",
        actor="alice",
        timestamp=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
    )
    assert e.event_kind == "field_change"
    assert e.field_name == "State"
    assert e.from_value == "Open"
    assert e.to_value == "Ready for testing"
    assert e.actor == "alice"
    assert e.from_state is None
    assert e.to_state is None


def test_issue_event_new_fields_default_to_none() -> None:
    e = IssueEvent(
        issue_id="DEMO-1",
        project="DEMO",
        event_kind="manual",
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
    )
    assert e.field_name is None
    assert e.from_value is None
    assert e.to_value is None
    assert e.actor is None


def test_issue_event_frozen() -> None:
    e = IssueEvent(
        issue_id="DEMO-1",
        project="DEMO",
        event_kind="manual",
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
    )
    with pytest.raises(ValidationError):
        e.issue_id = "DEMO-2"
