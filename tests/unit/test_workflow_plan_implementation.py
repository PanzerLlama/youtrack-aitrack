"""Validation test for the shipped plan-implementation workflow YAML."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from youtrack_aitrack.cli.init import scaffold
from youtrack_aitrack.cli.main import app
from youtrack_aitrack.config import load_workflow
from youtrack_aitrack.domain.actions.ai_report import AiReportAction
from youtrack_aitrack.domain.actions.bd_issue import BdIssueAction
from youtrack_aitrack.domain.actions.git_branch import GitBranchAction
from youtrack_aitrack.domain.output import CommentOutput
from youtrack_aitrack.domain.triggers.manual import ManualTrigger

_WORKFLOW_PATH = Path("workflows/plan-implementation.yaml")
_PROMPTS_DIR = Path("prompts")


def test_workflow_file_exists_and_loads() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    assert wf.name == "plan-implementation"


def test_trigger_is_manual() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    assert isinstance(wf.trigger, ManualTrigger)


def test_action_chain_branch_then_plan_then_save() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    assert [a.id for a in wf.actions] == ["create_branch", "implementation_plan", "track_plan"]
    branch, plan, track = wf.actions
    assert isinstance(branch, GitBranchAction)
    assert isinstance(plan, AiReportAction)
    assert isinstance(track, BdIssueAction)
    assert plan.depends_on == ["create_branch"]
    assert track.depends_on == ["implementation_plan"]


def test_branch_uses_default_template_and_base_from_config() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    branch = wf.actions[0]
    assert isinstance(branch, GitBranchAction)
    assert branch.name == "{task_id}-{slug}"
    assert branch.base is None
    assert branch.checkout is True
    assert branch.inputs == ["task_meta"]


def test_plan_runs_in_plan_mode_and_posts_a_comment() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    plan = wf.actions[1]
    assert isinstance(plan, AiReportAction)
    assert plan.mode == "plan"
    assert isinstance(plan.output, CommentOutput)
    assert (_PROMPTS_DIR / plan.prompt).is_file()


def test_track_plan_uses_beads_with_file_fallback() -> None:
    wf = load_workflow(_WORKFLOW_PATH, env={})
    track = wf.actions[2]
    assert isinstance(track, BdIssueAction)
    assert track.source == "implementation_plan"
    assert track.title == "{task_id}: {summary}"
    assert track.issue_type == "feature"
    assert track.external_ref == "{task_id}"
    assert track.fallback_path == "docs/plans/{task_id}.md"
    assert track.fallback_commit_message == "docs: implementation plan for {task_id}"


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

    result = CliRunner().invoke(app, ["--config-dir", str(cfg), "workflows", "validate"])
    assert result.exit_code == 0, result.output
