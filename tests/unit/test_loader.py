"""Tests for the workflow YAML loader, env expansion, and schema export."""

from __future__ import annotations

from pathlib import Path

import pytest

from youtrack_aitrack.config import (
    WorkflowParseError,
    expand_env,
    export_workflow_schema,
    load_workflow,
)
from youtrack_aitrack.domain.actions.ai_report import AiReportAction
from youtrack_aitrack.domain.actions.set_field import SetFieldAction
from youtrack_aitrack.domain.triggers.status_change import StatusChangeTrigger

VALID_YAML = """
name: ready-for-testing-audit
description: First reference workflow.
trigger:
  type: status_change
  to_state: "Ready for testing"
  from_state: "*"
actions:
  - id: security_audit
    type: ai_report
    inputs: [git_diff]
    output: { kind: custom_field, name: "Security Audit" }
    prompt: "audit prompt"
    model: claude-sonnet-4-6
on_success:
  - id: mark_done
    type: set_field
    fields: { "Audit Status": "done" }
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


# --- expand_env (pure) ---


def test_expand_env_substitutes_in_strings() -> None:
    out = expand_env("hello ${WHO}", {"WHO": "world"})
    assert out == "hello world"


def test_expand_env_recurses_into_lists_and_dicts() -> None:
    out = expand_env(
        {"a": ["${X}", {"b": "${Y}"}], "n": 1, "z": True},
        {"X": "1", "Y": "2"},
    )
    assert out == {"a": ["1", {"b": "2"}], "n": 1, "z": True}


def test_expand_env_missing_var_raises() -> None:
    with pytest.raises(WorkflowParseError) as exc:
        expand_env("${MISSING}", {})
    assert "MISSING" in str(exc.value)


def test_expand_env_leaves_non_var_dollars_alone() -> None:
    assert expand_env("price $5", {}) == "price $5"


# --- load_workflow (happy path) ---


def test_load_workflow_happy_path(tmp_path: Path) -> None:
    path = _write(tmp_path, "wf.yaml", VALID_YAML)
    wf = load_workflow(path, env={})
    assert wf.name == "ready-for-testing-audit"
    assert isinstance(wf.trigger, StatusChangeTrigger)
    assert wf.trigger.to_state == "Ready for testing"
    assert len(wf.actions) == 1
    assert isinstance(wf.actions[0], AiReportAction)
    assert wf.actions[0].model == "claude-sonnet-4-6"
    assert isinstance(wf.on_success[0], SetFieldAction)


def test_load_workflow_expands_env(tmp_path: Path) -> None:
    text = """
name: env-test
trigger: { type: manual }
actions:
  - id: a1
    type: ai_report
    prompt: "${PROMPT_TEXT}"
    model: "${MODEL_NAME}"
"""
    path = _write(tmp_path, "wf.yaml", text)
    wf = load_workflow(path, env={"PROMPT_TEXT": "hi", "MODEL_NAME": "claude-sonnet-4-6"})
    a = wf.actions[0]
    assert isinstance(a, AiReportAction)
    assert a.prompt == "hi"
    assert a.model == "claude-sonnet-4-6"


# --- failure modes ---


def test_invalid_yaml_reports_line(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad.yaml", "name: x\n  bad: : :\n")
    with pytest.raises(WorkflowParseError) as exc:
        load_workflow(path, env={})
    msg = str(exc.value)
    assert str(path) in msg


def test_root_must_be_mapping(tmp_path: Path) -> None:
    path = _write(tmp_path, "list.yaml", "- a\n- b\n")
    with pytest.raises(WorkflowParseError) as exc:
        load_workflow(path, env={})
    assert "mapping" in str(exc.value)


def test_unknown_trigger_type(tmp_path: Path) -> None:
    text = """
name: bad
trigger: { type: nope }
actions: []
"""
    path = _write(tmp_path, "wf.yaml", text)
    with pytest.raises(WorkflowParseError) as exc:
        load_workflow(path, env={})
    assert "nope" in str(exc.value)


def test_unknown_action_type(tmp_path: Path) -> None:
    text = """
name: bad
trigger: { type: manual }
actions:
  - id: a1
    type: not_a_real_action
"""
    path = _write(tmp_path, "wf.yaml", text)
    with pytest.raises(WorkflowParseError) as exc:
        load_workflow(path, env={})
    msg = str(exc.value)
    assert "actions[0]" in msg
    assert "not_a_real_action" in msg


def test_missing_required_action_field(tmp_path: Path) -> None:
    text = """
name: bad
trigger: { type: manual }
actions:
  - id: a1
    type: ai_report
    model: claude-sonnet-4-6
"""
    path = _write(tmp_path, "wf.yaml", text)
    with pytest.raises(WorkflowParseError) as exc:
        load_workflow(path, env={})
    msg = str(exc.value)
    assert "actions[0]" in msg
    assert "prompt" in msg


def test_missing_env_var_during_load(tmp_path: Path) -> None:
    text = """
name: env-fail
trigger: { type: manual }
actions:
  - id: a1
    type: ai_report
    prompt: "${MISSING_VAR}"
    model: claude-sonnet-4-6
"""
    path = _write(tmp_path, "wf.yaml", text)
    with pytest.raises(WorkflowParseError) as exc:
        load_workflow(path, env={})
    assert "MISSING_VAR" in str(exc.value)


def test_workflow_validation_error_propagates(tmp_path: Path) -> None:
    text = """
name: dup
trigger: { type: manual }
actions:
  - id: a1
    type: ai_report
    prompt: p
    model: m
  - id: a1
    type: ai_report
    prompt: p
    model: m
"""
    path = _write(tmp_path, "wf.yaml", text)
    with pytest.raises(WorkflowParseError) as exc:
        load_workflow(path, env={})
    assert "unique" in str(exc.value).lower()


# --- schema export ---


def test_export_workflow_schema_has_top_level_fields() -> None:
    schema = export_workflow_schema()
    assert schema["type"] == "object"
    props = schema["properties"]
    for key in ("name", "trigger", "actions", "on_success", "on_failure"):
        assert key in props
