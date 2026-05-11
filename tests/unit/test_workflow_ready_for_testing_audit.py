"""Validation test for the shipped reference workflow YAML."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from youtrack_aitrack.cli.init import scaffold
from youtrack_aitrack.cli.main import app
from youtrack_aitrack.config import load_workflow
from youtrack_aitrack.domain.actions.ai_report import AiReportAction
from youtrack_aitrack.domain.actions.set_field import SetFieldAction
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.output import CustomFieldOutput
from youtrack_aitrack.domain.triggers.status_change import StatusChangeTrigger

_WORKFLOW_PATH = Path("workflows/ready-for-testing-audit.yaml")
_PROMPTS_DIR = Path("prompts")


def test_workflow_file_exists_and_loads() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    assert wf.name == "ready-for-testing-audit"


def test_trigger_is_status_change_to_ready_for_testing() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    assert isinstance(wf.trigger, StatusChangeTrigger)
    assert wf.trigger.to_state == "Ready for testing"
    assert wf.trigger.from_state == "*"


def test_trigger_matches_status_change_event() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    assert isinstance(wf.trigger, StatusChangeTrigger)
    event = IssueEvent(
        issue_id="DEMO-1",
        project="DEMO",
        event_kind="status_change",
        from_state="In Progress",
        to_state="Ready for testing",
        timestamp=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
    )
    assert wf.trigger.matches(event) is True


def test_trigger_rejects_other_to_states() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    assert isinstance(wf.trigger, StatusChangeTrigger)
    event = IssueEvent(
        issue_id="DEMO-1",
        project="DEMO",
        event_kind="status_change",
        from_state="In Progress",
        to_state="Done",
        timestamp=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
    )
    assert wf.trigger.matches(event) is False


def test_three_ai_report_actions_with_correct_ids() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    ids = [a.id for a in wf.actions]
    assert ids == ["security_audit", "pages_changed", "qa_plan"]
    for action in wf.actions:
        assert isinstance(action, AiReportAction)
        assert action.model == "claude-sonnet-4-6"


def test_qa_plan_depends_on_pages_changed() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    qa_plan = next(a for a in wf.actions if a.id == "qa_plan")
    assert qa_plan.depends_on == ["pages_changed"]
    security = next(a for a in wf.actions if a.id == "security_audit")
    pages = next(a for a in wf.actions if a.id == "pages_changed")
    assert security.depends_on == []
    assert pages.depends_on == []


def test_each_action_writes_to_custom_field() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    expected_field_names = {
        "security_audit": "Security Audit",
        "pages_changed": "Pages Changed",
        "qa_plan": "QA Plan",
    }
    for action in wf.actions:
        assert isinstance(action.output, CustomFieldOutput)
        assert action.output.name == expected_field_names[action.id]


def test_each_prompt_path_resolves_under_prompts_dir() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    for action in wf.actions:
        assert isinstance(action, AiReportAction)
        resolved = _PROMPTS_DIR / action.prompt
        assert resolved.is_file(), f"missing prompt template: {resolved}"


def test_hooks_set_audit_status_field() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    [success] = wf.on_success
    [failure] = wf.on_failure
    assert isinstance(success, SetFieldAction)
    assert isinstance(failure, SetFieldAction)
    assert success.fields == {"Audit Status": "done"}
    assert failure.fields == {"Audit Status": "failed"}


def test_yta_workflows_validate_exits_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("YOUTRACK_URL", "https://yt.example.com")
    monkeypatch.setenv("YOUTRACK_TOKEN", "tok")
    monkeypatch.setenv("YOUTRACK_PROJECT", "DEMO")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    cfg = tmp_path / "cfg"
    scaffold(cfg)
    (cfg / "workflows" / _WORKFLOW_PATH.name).write_text(_WORKFLOW_PATH.read_text())

    runner = CliRunner()
    result = runner.invoke(app, ["--config-dir", str(cfg), "workflows", "validate"])
    assert result.exit_code == 0, result.output
