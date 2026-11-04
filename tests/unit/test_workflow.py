"""Tests for Workflow validation, round-trip, and YAML loading."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.output import CustomFieldOutput
from youtrack_aitrack.domain.trigger import TriggerSpec
from youtrack_aitrack.domain.workflow import Workflow, select_actions

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


def test_workflow_on_success_depends_on_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Workflow(
            name="bad",
            trigger=_trigger(),
            actions=[ActionSpec(id="a1", type="ai_report")],
            on_success=[
                ActionSpec(id="ok", type="set_field", depends_on=["a1"]),
            ],
        )
    assert "on_success" in str(exc.value)


def test_workflow_on_failure_depends_on_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Workflow(
            name="bad",
            trigger=_trigger(),
            actions=[ActionSpec(id="a1", type="ai_report")],
            on_failure=[
                ActionSpec(id="fail", type="set_field", depends_on=["a1"]),
            ],
        )
    assert "on_failure" in str(exc.value)


def _chain_workflow() -> Workflow:
    """diff -> pages -> qa, plus an independent audit; hooks on both ends."""
    return Workflow(
        name="audit",
        trigger=_trigger(),
        actions=[
            ActionSpec(id="diff", type="set_field"),
            ActionSpec(id="audit", type="set_field"),
            ActionSpec(id="pages", type="set_field", depends_on=["diff"]),
            ActionSpec(id="qa", type="set_field", depends_on=["pages"]),
        ],
        on_success=[ActionSpec(id="done", type="set_field")],
        on_failure=[ActionSpec(id="failed", type="set_field")],
    )


def test_select_actions_keeps_only_requested_action_and_drops_hooks() -> None:
    selected = select_actions(_chain_workflow(), ["audit"])

    assert [a.id for a in selected.actions] == ["audit"]
    assert selected.on_success == []
    assert selected.on_failure == []
    assert selected.name == "audit"


def test_select_actions_includes_transitive_depends_on_in_original_order() -> None:
    selected = select_actions(_chain_workflow(), ["qa"])

    assert [a.id for a in selected.actions] == ["diff", "pages", "qa"]


def test_select_actions_accepts_several_ids_without_duplicates() -> None:
    selected = select_actions(_chain_workflow(), ["pages", "audit", "diff"])

    assert [a.id for a in selected.actions] == ["diff", "audit", "pages"]


def test_select_actions_unknown_id_lists_available_ids() -> None:
    with pytest.raises(ValueError, match=r"no action\(s\) \['nope'\]") as exc:
        select_actions(_chain_workflow(), ["qa", "nope"])

    assert "['diff', 'audit', 'pages', 'qa']" in str(exc.value)


def test_select_actions_leaves_original_workflow_untouched() -> None:
    wf = _chain_workflow()
    select_actions(wf, ["audit"])

    assert len(wf.actions) == 4
    assert len(wf.on_success) == 1
