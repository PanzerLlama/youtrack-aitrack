"""Tests for Runner — repo state resolution + dispatch."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from youtrack_aitrack.adapters.git.diff import GitDiffError
from youtrack_aitrack.config.instance import (
    AnthropicSection,
    DefaultsSection,
    InstanceConfig,
    PathsSection,
    YouTrackSection,
)
from youtrack_aitrack.domain.actions.ai_report import AiReportAction
from youtrack_aitrack.domain.actions.set_field import SetFieldAction
from youtrack_aitrack.domain.agent_runner import AgentResult
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.run import RunReport, RunState
from youtrack_aitrack.domain.triggers.manual import ManualTrigger
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.engine import WorkflowEngine
from youtrack_aitrack.runtime.factory import ActionFactory
from youtrack_aitrack.runtime.runner import Runner


class _FakeGit:
    def __init__(
        self,
        *,
        branch: str | None = "DEMO-1-fix",
        diff: str = "diff --git a/x b/x\n",
        sha: str = "deadbeef",
        resolve_error: bool = False,
        diff_error: bool = False,
    ) -> None:
        self._branch = branch
        self._diff = diff
        self._sha = sha
        self._resolve_error = resolve_error
        self._diff_error = diff_error
        self.resolve_calls: list[tuple[str, Path, str]] = []
        self.diff_calls: list[tuple[Path, str, str]] = []
        self.sha_calls: list[tuple[Path, str]] = []

    def resolve_branch(self, task_id: str, *, repo_dir: Path, pattern: str) -> str | None:
        self.resolve_calls.append((task_id, repo_dir, pattern))
        if self._resolve_error:
            raise GitDiffError("boom")
        return self._branch

    def diff(self, repo_dir: Path, branch: str, base: str = "main") -> str:
        self.diff_calls.append((repo_dir, branch, base))
        if self._diff_error:
            raise GitDiffError("boom")
        return self._diff

    def commit_sha(self, repo_dir: Path, branch: str) -> str:
        self.sha_calls.append((repo_dir, branch))
        return self._sha


class _FakeLLM:
    """AgentRunner test double. Kept the historical _FakeLLM name to minimise churn."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        commit_sha: str | None,
        timeout_s: float,
        model: str | None = None,
    ) -> AgentResult:
        self.calls.append((prompt, model or ""))
        return AgentResult(output="ai-output", exit_code=0, duration_s=0.0, model_used=model)


class _FakeRenderer:
    def render(self, template: str, ctx: Context) -> str:
        return (
            f"branch={ctx.branch}|diff={ctx.diff}|base_url={ctx.base_url}|"
            f"commit_sha={ctx.commit_sha}|repo_path={ctx.repo_path}|tmpl={template}"
        )


class _FakeWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None:
        self.calls.append((issue_id, fields))


class _FakePoster:
    async def post_comment(self, issue_id: str, body: str) -> None:
        return None


class _FakeStateLookup:
    def __init__(self, state: str | None = None) -> None:
        self.state = state
        self.calls: list[str] = []

    async def get_issue_state(self, issue_id: str) -> str | None:
        self.calls.append(issue_id)
        return self.state


class _FakeRunStore:
    def __init__(self) -> None:
        self.saved: list[RunReport] = []
        self._idem: dict[str, str] = {}

    def save_run(self, report: RunReport) -> None:
        self.saved.append(report)

    def load_run(self, run_id: str) -> RunReport | None:
        return next((r for r in self.saved if r.run_id == run_id), None)

    def save_cursor(self, token: str | None) -> None:
        return None

    def load_cursor(self) -> str | None:
        return None

    def has_processed(self, key: str) -> bool:
        return key in self._idem

    def mark_processed(self, key: str, run_id: str) -> None:
        self._idem[key] = run_id


def _config(*, base_url: str | None = None, git_base_branch: str = "main") -> InstanceConfig:
    return InstanceConfig(
        youtrack=YouTrackSection(url="https://yt.example.com", token="t", project="DEMO"),
        anthropic=AnthropicSection(api_key="k"),
        paths=PathsSection(),
        defaults=DefaultsSection(
            branch_pattern="{task_id}-*", base_url=base_url, git_base_branch=git_base_branch
        ),
    )


def _manual_event(issue_id: str = "DEMO-1") -> IssueEvent:
    return IssueEvent(
        issue_id=issue_id,
        project="DEMO",
        event_kind="manual",
        timestamp=datetime(2026, 5, 11, tzinfo=UTC),
    )


def _build(
    *,
    git: _FakeGit,
    workflow: Workflow,
    llm: _FakeLLM | None = None,
    writer: _FakeWriter | None = None,
    run_store: _FakeRunStore | None = None,
    state_lookup: _FakeStateLookup | None = None,
    base_url: str | None = None,
    git_base_branch: str = "main",
) -> tuple[Runner, _FakeLLM, _FakeWriter, _FakeRunStore, _FakeStateLookup]:
    llm = llm or _FakeLLM()
    writer = writer or _FakeWriter()
    run_store = run_store or _FakeRunStore()
    state_lookup = state_lookup or _FakeStateLookup()
    factory = ActionFactory(
        agents={"anthropic_api": llm},
        default_agent="anthropic_api",
        renderer=_FakeRenderer(),
        writer=writer,
        poster=_FakePoster(),
    )
    workflows = [factory.materialize_workflow(workflow)]
    runner = Runner(
        config=_config(base_url=base_url, git_base_branch=git_base_branch),
        workflows=workflows,
        engine=WorkflowEngine(idempotency_store=run_store),
        git_provider=git,
        repo_dir=Path("/tmp/fakerepo"),
        run_store=run_store,
        state_lookup=state_lookup,
    )
    return runner, llm, writer, run_store, state_lookup


async def test_dispatch_resolves_branch_diff_sha_and_runs_ai_report() -> None:
    git = _FakeGit()
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[
            AiReportAction(
                id="audit",
                inputs=["git_diff"],
                prompt="security_audit.md",
                model="claude-sonnet-4-6",
            )
        ],
    )
    runner, llm, _, run_store, _ = _build(git=git, workflow=wf)

    [report] = await runner.dispatch(_manual_event())

    assert report.state is RunState.DONE
    assert git.resolve_calls == [("DEMO-1", Path("/tmp/fakerepo"), "{task_id}-*")]
    assert git.diff_calls == [(Path("/tmp/fakerepo"), "DEMO-1-fix", "main")]
    assert git.sha_calls == [(Path("/tmp/fakerepo"), "DEMO-1-fix")]
    assert len(llm.calls) == 1
    rendered_prompt, model = llm.calls[0]
    assert "branch=DEMO-1-fix" in rendered_prompt
    assert "diff=diff --git a/x b/x\n" in rendered_prompt
    assert model == "claude-sonnet-4-6"
    assert run_store.saved == [report]


async def test_dispatch_no_branch_marks_git_diff_unavailable() -> None:
    git = _FakeGit(branch=None)
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[
            AiReportAction(
                id="audit",
                inputs=["git_diff"],
                prompt="security_audit.md",
                model="m",
            )
        ],
    )
    runner, llm, _, _, _ = _build(git=git, workflow=wf)

    [report] = await runner.dispatch(_manual_event())

    assert report.state is RunState.DONE
    assert report.action_results[0].skipped is True
    assert llm.calls == []
    assert git.diff_calls == []
    assert git.sha_calls == []


async def test_dispatch_resolve_branch_error_marks_unavailable() -> None:
    git = _FakeGit(resolve_error=True)
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[AiReportAction(id="a", inputs=["git_diff"], prompt="p.md", model="m")],
    )
    runner, llm, _, _, _ = _build(git=git, workflow=wf)

    [report] = await runner.dispatch(_manual_event())

    assert report.action_results[0].skipped is True
    assert llm.calls == []


async def test_dispatch_diff_error_after_branch_resolved_still_skips() -> None:
    git = _FakeGit(diff_error=True)
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[AiReportAction(id="a", inputs=["git_diff"], prompt="p.md", model="m")],
    )
    runner, llm, _, _, _ = _build(git=git, workflow=wf)

    [report] = await runner.dispatch(_manual_event())

    assert report.action_results[0].skipped is True
    assert llm.calls == []


async def test_run_fabricates_status_change_event_from_current_state() -> None:
    git = _FakeGit()
    from youtrack_aitrack.domain.triggers.status_change import StatusChangeTrigger

    wf = Workflow(
        name="audit",
        trigger=StatusChangeTrigger(to_state="Ready for testing"),
        actions=[SetFieldAction(id="s", fields={"Status": "audited"})],
    )
    state_lookup = _FakeStateLookup(state="Ready for testing")
    runner, _, writer, _, _ = _build(git=git, workflow=wf, state_lookup=state_lookup)

    reports = await runner.run("DEMO-7")

    assert state_lookup.calls == ["DEMO-7"]
    assert len(reports) == 1
    assert writer.calls == [("DEMO-7", {"Status": "audited"})]


async def test_run_returns_empty_when_state_does_not_match_any_trigger() -> None:
    git = _FakeGit()
    from youtrack_aitrack.domain.triggers.status_change import StatusChangeTrigger

    wf = Workflow(
        name="audit",
        trigger=StatusChangeTrigger(to_state="Ready for testing"),
        actions=[SetFieldAction(id="s", fields={"Status": "audited"})],
    )
    state_lookup = _FakeStateLookup(state="In progress")
    runner, _, writer, _, _ = _build(git=git, workflow=wf, state_lookup=state_lookup)

    reports = await runner.run("DEMO-7")

    assert reports == []
    assert writer.calls == []


async def test_dispatch_forwards_base_url_from_config_to_engine() -> None:
    git = _FakeGit()
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[
            AiReportAction(id="a", inputs=["git_diff"], prompt="p.md", model="m"),
        ],
    )
    runner, llm, _, _, _ = _build(git=git, workflow=wf, base_url="https://app.example.com")

    await runner.dispatch(_manual_event())

    assert len(llm.calls) == 1
    rendered_prompt, _model = llm.calls[0]
    assert "base_url=https://app.example.com" in rendered_prompt


async def test_dispatch_forwards_git_base_branch_to_diff_adapter() -> None:
    git = _FakeGit()
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[AiReportAction(id="a", inputs=["git_diff"], prompt="p.md", model="m")],
    )
    runner, _, _, _, _ = _build(git=git, workflow=wf, git_base_branch="develop")

    await runner.dispatch(_manual_event())

    assert git.diff_calls == [(Path("/tmp/fakerepo"), "DEMO-1-fix", "develop")]


async def test_dispatch_uses_main_as_default_git_base_branch() -> None:
    git = _FakeGit()
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[AiReportAction(id="a", inputs=["git_diff"], prompt="p.md", model="m")],
    )
    runner, _, _, _, _ = _build(git=git, workflow=wf)

    await runner.dispatch(_manual_event())

    assert git.diff_calls == [(Path("/tmp/fakerepo"), "DEMO-1-fix", "main")]


async def test_dispatch_base_url_none_when_config_unset() -> None:
    git = _FakeGit()
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[AiReportAction(id="a", inputs=["git_diff"], prompt="p.md", model="m")],
    )
    runner, llm, _, _, _ = _build(git=git, workflow=wf)

    await runner.dispatch(_manual_event())

    rendered_prompt, _model = llm.calls[0]
    assert "base_url=None" in rendered_prompt


async def test_dispatch_threads_commit_sha_and_repo_path_into_context() -> None:
    git = _FakeGit(sha="cafef00d")
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[AiReportAction(id="a", inputs=["git_diff"], prompt="p.md", model="m")],
    )
    runner, llm, _, _, _ = _build(git=git, workflow=wf)

    await runner.dispatch(_manual_event())

    rendered_prompt, _model = llm.calls[0]
    assert "commit_sha=cafef00d" in rendered_prompt
    assert "repo_path=/tmp/fakerepo" in rendered_prompt


async def test_dispatch_repo_path_present_even_when_git_diff_unavailable() -> None:
    git = _FakeGit(branch=None)
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[
            AiReportAction(id="a", inputs=[], prompt="p.md", model="m"),
        ],
    )
    runner, llm, _, _, _ = _build(git=git, workflow=wf)

    await runner.dispatch(_manual_event())

    rendered_prompt, _model = llm.calls[0]
    assert "repo_path=/tmp/fakerepo" in rendered_prompt
    assert "commit_sha=None" in rendered_prompt


async def test_run_force_bypasses_idempotency() -> None:
    git = _FakeGit()
    from youtrack_aitrack.domain.triggers.status_change import StatusChangeTrigger

    wf = Workflow(
        name="audit",
        trigger=StatusChangeTrigger(to_state="Ready for testing"),
        actions=[SetFieldAction(id="s", fields={"Status": "audited"})],
    )
    state_lookup = _FakeStateLookup(state="Ready for testing")
    runner, _, writer, _, _ = _build(git=git, workflow=wf, state_lookup=state_lookup)

    await runner.run("DEMO-7")
    await runner.run("DEMO-7")
    await runner.run("DEMO-7", force=True)

    assert len(writer.calls) == 2


async def test_dispatch_action_outputs_flow_between_actions() -> None:
    git = _FakeGit()
    wf = Workflow(
        name="chain",
        trigger=ManualTrigger(),
        actions=[
            AiReportAction(id="parent", inputs=["git_diff"], prompt="p.md", model="m"),
            AiReportAction(
                id="child",
                depends_on=["parent"],
                inputs=["dependency_outputs"],
                prompt="p.md",
                model="m",
            ),
        ],
    )
    runner, llm, _, _, _ = _build(git=git, workflow=wf)

    [report] = await runner.dispatch(_manual_event())

    assert report.state is RunState.DONE
    assert {r.action_id for r in report.action_results} == {"parent", "child"}
    assert len(llm.calls) == 2


async def test_idempotency_dedupes_repeat_dispatch_for_same_commit() -> None:
    git = _FakeGit()
    wf = Workflow(
        name="audit",
        trigger=ManualTrigger(),
        actions=[AiReportAction(id="a", inputs=["git_diff"], prompt="p.md", model="m")],
    )
    runner, llm, _, _, _ = _build(git=git, workflow=wf)

    first = await runner.dispatch(_manual_event())
    second = await runner.dispatch(_manual_event())

    assert len(first) == 1
    assert second == []
    assert len(llm.calls) == 1


@pytest.mark.parametrize("branch", [None, ""])
def test_resolve_repo_state_empty_branch_marks_unavailable(branch: str | None) -> None:
    git = _FakeGit(branch=branch or None)
    runner, _, _, _, _ = _build(
        git=git,
        workflow=Workflow(
            name="x",
            trigger=ManualTrigger(),
            actions=[AiReportAction(id="a", prompt="p.md", model="m")],
        ),
    )
    b, d, sha, unavailable = cast(
        tuple[str | None, str | None, str | None, set[str]],
        runner._resolve_repo_state("DEMO-1"),
    )
    assert b is None and d is None and sha is None
    assert unavailable == {"git_diff"}
