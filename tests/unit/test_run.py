"""Tests for RunState and ActionResult."""

import pytest
from pydantic import ValidationError

from youtrack_aitrack.domain.run import ActionResult, RunState


def test_run_state_values() -> None:
    assert {s.value for s in RunState} == {"pending", "running", "done", "failed"}


def test_action_result_minimal() -> None:
    r = ActionResult(action_id="a1", success=True)
    assert r.action_id == "a1"
    assert r.success is True
    assert r.output is None


def test_action_result_with_output() -> None:
    r = ActionResult(
        action_id="security_audit",
        success=True,
        output={"summary": "no issues"},
        duration_ms=1234,
    )
    assert r.output == {"summary": "no issues"}
    assert r.duration_ms == 1234


def test_action_result_frozen() -> None:
    r = ActionResult(action_id="a1", success=True)
    with pytest.raises(ValidationError):
        r.success = False


def test_action_result_missing_required_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionResult(action_id="a1")
