"""Tests for Workflow validation, round-trip, and YAML loading."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.output import CustomFieldOutput
from youtrack_aitrack.domain.trigger import TriggerSpec
from youtrack_aitrack.domain.workflow import Workflow

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _trigger(**fields: object) -> TriggerSpec:
    return TriggerSpec(type="status_change", **fields)


def test_workflow_basic() -> None:
    w = Workflow(
        name="audit",
        trigger=_trigger(to_state="Ready for testing"),
        actions=[ActionSpec(id="a1", type="ai_report")],
    )
    assert w.name == "audit"
    assert w.actions[0].id == "a1"


def test_workflow_round_trip_via_dict() -> None:
    w = Workflow(
        name="audit",
        trigger=_trigger(to_state="Ready for testing"),
        actions=[
            ActionSpec(
                id="a1",
                type="ai_report",
                output=CustomFieldOutput(name="Security Audit"),
            ),
            ActionSpec(id="a2", type="ai_report", depends_on=["a1"]),
        ],
    )
    restored = Workflow.model_validate(w.model_dump())
    assert restored == w


def test_workflow_loads_from_yaml_fixture() -> None:
    raw = yaml.safe_load((_FIXTURES / "sample_workflow.yaml").read_text())
    w = Workflow.model_validate(raw)
    assert w.name == "ready-for-testing-audit"
    assert len(w.actions) == 3
    assert w.actions[2].depends_on == ["pages_changed"]


def test_workflow_duplicate_action_id_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Workflow(
            name="bad",
            trigger=_trigger(),
            actions=[
                ActionSpec(id="a1", type="ai_report"),
                ActionSpec(id="a1", type="ai_report"),
            ],
        )
    assert "unique" in str(exc.value).lower()


def test_workflow_unknown_dependency_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Workflow(
            name="bad",
            trigger=_trigger(),
            actions=[ActionSpec(id="a1", type="ai_report", depends_on=["missing"])],
        )
    assert "missing" in str(exc.value)


def test_workflow_self_dependency_rejected() -> None:
    with pytest.raises(ValidationError):
        Workflow(
            name="bad",
            trigger=_trigger(),
            actions=[ActionSpec(id="a1", type="ai_report", depends_on=["a1"])],
        )


def test_workflow_frozen() -> None:
    w = Workflow(
        name="audit",
        trigger=_trigger(),
        actions=[ActionSpec(id="a1", type="ai_report")],
    )
    with pytest.raises(ValidationError):
        w.name = "renamed"
