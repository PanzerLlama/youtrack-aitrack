"""Tests for status_change and manual triggers."""

from datetime import UTC, datetime

# Importing the package executes the @register_trigger decorators.
import youtrack_aitrack.domain.triggers  # noqa: F401
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.triggers.manual import ManualTrigger
from youtrack_aitrack.domain.triggers.status_change import StatusChangeTrigger
from youtrack_aitrack.registry import trigger_registry


def _status_change(
    from_state: str | None = "Open",
    to_state: str | None = "Ready for testing",
) -> IssueEvent:
    return IssueEvent(
        issue_id="DEMO-1",
        project="DEMO",
        event_kind="status_change",
        from_state=from_state,
        to_state=to_state,
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
    )


def _manual_event() -> IssueEvent:
    return IssueEvent(
        issue_id="DEMO-1",
        project="DEMO",
        event_kind="manual",
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
    )


# --- StatusChangeTrigger ---


def test_status_change_exact_match() -> None:
    t = StatusChangeTrigger(from_state="Open", to_state="Ready for testing")
    assert t.matches(_status_change()) is True


def test_status_change_wildcard_from() -> None:
    t = StatusChangeTrigger(from_state="*", to_state="Ready for testing")
    assert t.matches(_status_change(from_state="Anything")) is True


def test_status_change_wildcard_default() -> None:
    t = StatusChangeTrigger(to_state="Ready for testing")
    assert t.matches(_status_change(from_state="In Progress")) is True


def test_status_change_from_state_mismatch() -> None:
    t = StatusChangeTrigger(from_state="In Progress", to_state="Ready for testing")
    assert t.matches(_status_change(from_state="Open")) is False


def test_status_change_to_state_mismatch() -> None:
    t = StatusChangeTrigger(from_state="*", to_state="Done")
    assert t.matches(_status_change(to_state="Ready for testing")) is False


def test_status_change_ignores_manual_event() -> None:
    t = StatusChangeTrigger(from_state="*", to_state="Done")
    assert t.matches(_manual_event()) is False


# --- ManualTrigger ---


def test_manual_matches_manual_event() -> None:
    t = ManualTrigger()
    assert t.matches(_manual_event()) is True


def test_manual_ignores_status_change() -> None:
    t = ManualTrigger()
    assert t.matches(_status_change()) is False


# --- Registration ---


def test_status_change_registered() -> None:
    assert trigger_registry.get("status_change") is StatusChangeTrigger


def test_manual_registered() -> None:
    assert trigger_registry.get("manual") is ManualTrigger
