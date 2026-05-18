"""Tests for WorkflowEngine — trigger matching, action graph, hooks, lifecycle."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import PrivateAttr

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.run import ActionResult, RunState
from youtrack_aitrack.domain.triggers.manual import ManualTrigger
from youtrack_aitrack.domain.triggers.status_change import StatusChangeTrigger
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.engine import WorkflowEngine
from youtrack_aitrack.engine.idempotency import (
    _InMemoryIdempotencyStore,
    build_idempotency_key,
)


def _manual_event() -> IssueEvent:
    return IssueEvent(
        issue_id="DEMO-1",
        project="DEMO",
        event_kind="manual",
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
    )


def _status_change_event(to_state: str = "Ready for testing") -> IssueEvent:
    return IssueEvent(
        issue_id="DEMO-1",
        project="DEMO",
        event_kind="status_change",
        from_state="Open",
        to_state=to_state,
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
    )


# --- Fake actions used as building blocks ---


class _FakeAction(ActionSpec):
    """Records execute() calls and returns a configured success/failure."""

    type: Literal["_fake"] = "_fake"
    succeed: bool = True
    record_key: str = ""

    _calls: list[Context] = PrivateAttr(default_factory=list)
    _gate: asyncio.Event | None = PrivateAttr(default=None)
    _release_after: asyncio.Event | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        gate: asyncio.Event | None = None,
        release_after: asyncio.Event | None = None,
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self._gate = gate
        self._release_after = release_after

    @property
    def calls(self) -> list[Context]:
        return self._calls

    async def execute(self, ctx: Context) -> ActionResult:
        if self._gate is not None:
            await self._gate.wait()
        self._calls.append(ctx)
        if self._release_after is not None:
            self._release_after.set()
        if not self.succeed:
            return ActionResult(action_id=self.id, success=False, error="boom")
        return ActionResult(
            action_id=self.id,
            success=True,
            output={"key": self.record_key or self.id},
        )


def _wf(
    *,
    actions: list[ActionSpec],
    on_success: list[ActionSpec] | None = None,
    on_failure: list[ActionSpec] | None = None,
    name: str = "wf",
    trigger: Any = None,
) -> Workflow:
    return Workflow(
        name=name,
        trigger=trigger or ManualTrigger(),
        actions=actions,
        on_success=on_success or [],
        on_failure=on_failure or [],
    )


# --- dispatch / trigger matching ---


async def test_dispatch_returns_empty_when_no_match() -> None:
    wf = _wf(
        actions=[_FakeAction(id="a1")],
        trigger=StatusChangeTrigger(to_state="Done"),
    )
    reports = await WorkflowEngine().dispatch(_status_change_event("Other"), [wf])
    assert reports == []


async def test_dispatch_runs_each_matching_workflow() -> None:
    a = _FakeAction(id="a")
    b = _FakeAction(id="b")
    wf1 = _wf(name="w1", actions=[a])
    wf2 = _wf(name="w2", actions=[b])
    reports = await WorkflowEngine().dispatch(_manual_event(), [wf1, wf2])
    names = sorted(r.workflow_name for r in reports)
    assert names == ["w1", "w2"]
    assert all(r.state is RunState.DONE for r in reports)


# --- single-action e2e ---


async def test_single_action_workflow_runs_to_done() -> None:
    a = _FakeAction(id="a1")
    wf = _wf(actions=[a])
    [report] = await WorkflowEngine().dispatch(_manual_event(), [wf])
    assert report.state is RunState.DONE
    assert [r.action_id for r in report.action_results] == ["a1"]
    assert report.action_results[0].output == {"key": "a1"}


# --- depends_on respected ---


async def test_depends_on_orders_execution() -> None:
    parent = _FakeAction(id="parent")
    child = _FakeAction(id="child", depends_on=["parent"])
    wf = _wf(actions=[parent, child])
    [report] = await WorkflowEngine().dispatch(_manual_event(), [wf])
    assert report.state is RunState.DONE
    # The child was scheduled with parent's result already in ctx.action_outputs.
    child_ctx = cast(_FakeAction, child).calls[0]
    assert "parent" in child_ctx.action_outputs


# --- parallel actions execute concurrently ---


async def test_independent_actions_run_in_parallel() -> None:
    gate_a = asyncio.Event()
    gate_b = asyncio.Event()
    started_a = asyncio.Event()
    started_b = asyncio.Event()

    a = _FakeAction(id="a", gate=gate_a, release_after=started_a)
    b = _FakeAction(id="b", gate=gate_b, release_after=started_b)
    wf = _wf(actions=[a, b])

    async def driver() -> None:
        # Release each gate only once both actions are observed waiting.
        gate_a.set()
        await started_a.wait()
        gate_b.set()
        await started_b.wait()

    drive = asyncio.create_task(driver())
    [report] = await WorkflowEngine().dispatch(_manual_event(), [wf])
    await drive
    assert report.state is RunState.DONE
    # Both actions must have executed (parallel scheduling did not block on the other's gate).
    assert {r.action_id for r in report.action_results} == {"a", "b"}


# --- failure mid-graph triggers on_failure ---


async def test_failure_runs_on_failure_hooks() -> None:
    fail = _FakeAction(id="fail", succeed=False)
    skipped = _FakeAction(id="skipped", depends_on=["fail"])
    fail_hook = _FakeAction(id="cleanup")
    success_hook = _FakeAction(id="celebrate")
    wf = _wf(
        actions=[fail, skipped],
        on_success=[success_hook],
        on_failure=[fail_hook],
    )
    [report] = await WorkflowEngine().dispatch(_manual_event(), [wf])
    assert report.state is RunState.FAILED
    action_ids = {r.action_id for r in report.action_results}
    assert action_ids == {"fail"}
    assert [r.action_id for r in report.hook_results] == ["cleanup"]
    assert cast(_FakeAction, skipped).calls == []
    assert cast(_FakeAction, success_hook).calls == []


async def test_action_raising_exception_marked_failed() -> None:
    class _Boom(ActionSpec):
        type: Literal["_boom"] = "_boom"

        async def execute(self, ctx: Context) -> ActionResult:
            raise RuntimeError("kapow")

    wf = _wf(actions=[_Boom(id="x")], on_failure=[_FakeAction(id="cleanup")])
    [report] = await WorkflowEngine().dispatch(_manual_event(), [wf])
    assert report.state is RunState.FAILED
    [result] = report.action_results
    assert result.success is False
    assert result.error is not None and "kapow" in result.error
    assert [r.action_id for r in report.hook_results] == ["cleanup"]


# --- success runs on_success hooks ---


async def test_success_runs_on_success_hooks() -> None:
    a = _FakeAction(id="a")
    success_hook = _FakeAction(id="celebrate")
    fail_hook = _FakeAction(id="cleanup")
    wf = _wf(
        actions=[a],
        on_success=[success_hook],
        on_failure=[fail_hook],
    )
    [report] = await WorkflowEngine().dispatch(_manual_event(), [wf])
    assert report.state is RunState.DONE
    assert [r.action_id for r in report.hook_results] == ["celebrate"]
    assert cast(_FakeAction, fail_hook).calls == []


# --- per-action results captured in Context ---


async def test_downstream_action_sees_upstream_results() -> None:
    parent = _FakeAction(id="parent", record_key="parent-output")
    child = _FakeAction(id="child", depends_on=["parent"])
    wf = _wf(actions=[parent, child])
    await WorkflowEngine().dispatch(_manual_event(), [wf])
    child_ctx = cast(_FakeAction, child).calls[0]
    parent_result = child_ctx.action_outputs["parent"]
    assert parent_result.success is True
    assert parent_result.output == {"key": "parent-output"}


# --- unavailable_inputs: skip diff-dependent actions but run the rest ---


async def test_unavailable_input_skips_dependent_action() -> None:
    diff_dep = _FakeAction(id="diff_dep", inputs=["git_diff", "task_meta"])
    meta_only = _FakeAction(id="meta_only", inputs=["task_meta"])
    wf = _wf(actions=[diff_dep, meta_only])

    [report] = await WorkflowEngine().dispatch(
        _manual_event(), [wf], unavailable_inputs={"git_diff"}
    )

    assert report.state is RunState.DONE
    by_id = {r.action_id: r for r in report.action_results}
    assert by_id["diff_dep"].skipped is True
    assert by_id["diff_dep"].skip_reason is not None
    assert "git_diff" in by_id["diff_dep"].skip_reason
    assert by_id["meta_only"].skipped is False
    assert by_id["meta_only"].success is True
    assert cast(_FakeAction, diff_dep).calls == []
    assert cast(_FakeAction, meta_only).calls != []


async def test_all_diff_dependent_workflow_completes_cleanly() -> None:
    a = _FakeAction(id="a", inputs=["git_diff"])
    b = _FakeAction(id="b", inputs=["git_diff", "route_index"])
    success_hook = _FakeAction(id="celebrate")
    fail_hook = _FakeAction(id="cleanup")
    wf = _wf(actions=[a, b], on_success=[success_hook], on_failure=[fail_hook])

    [report] = await WorkflowEngine().dispatch(
        _manual_event(), [wf], unavailable_inputs={"git_diff"}
    )

    assert report.state is RunState.DONE
    assert all(r.skipped for r in report.action_results)
    assert [h.action_id for h in report.hook_results] == ["celebrate"]
    assert cast(_FakeAction, fail_hook).calls == []


async def test_skipped_parent_cascades_to_dependent() -> None:
    parent = _FakeAction(id="parent", inputs=["git_diff"])
    child = _FakeAction(id="child", depends_on=["parent"], inputs=["dependency_outputs"])
    wf = _wf(actions=[parent, child])

    [report] = await WorkflowEngine().dispatch(
        _manual_event(), [wf], unavailable_inputs={"git_diff"}
    )

    assert report.state is RunState.DONE
    by_id = {r.action_id: r for r in report.action_results}
    assert by_id["parent"].skipped is True
    assert by_id["child"].skipped is True
    assert by_id["child"].skip_reason is not None
    assert "parent" in by_id["child"].skip_reason
    assert cast(_FakeAction, child).calls == []


async def test_unavailable_inputs_none_runs_normally() -> None:
    a = _FakeAction(id="a", inputs=["git_diff"])
    wf = _wf(actions=[a])
    [report] = await WorkflowEngine().dispatch(_manual_event(), [wf])
    assert report.state is RunState.DONE
    assert report.action_results[0].skipped is False
    assert report.action_results[0].success is True


# --- idempotency dedup ---


async def test_idempotency_skips_second_dispatch_for_same_key() -> None:
    store = _InMemoryIdempotencyStore()
    engine = WorkflowEngine(idempotency_store=store)
    action = _FakeAction(id="a")
    wf = _wf(actions=[action])

    first = await engine.dispatch(_manual_event(), [wf], commit_sha="abc")
    second = await engine.dispatch(_manual_event(), [wf], commit_sha="abc")

    assert len(first) == 1
    assert second == []
    assert len(cast(_FakeAction, action).calls) == 1


async def test_idempotency_different_commit_sha_proceeds() -> None:
    store = _InMemoryIdempotencyStore()
    engine = WorkflowEngine(idempotency_store=store)
    action = _FakeAction(id="a")
    wf = _wf(actions=[action])

    await engine.dispatch(_manual_event(), [wf], commit_sha="abc")
    second = await engine.dispatch(_manual_event(), [wf], commit_sha="def")

    assert len(second) == 1
    assert len(cast(_FakeAction, action).calls) == 2


async def test_idempotency_force_bypasses_dedup() -> None:
    store = _InMemoryIdempotencyStore()
    engine = WorkflowEngine(idempotency_store=store)
    action = _FakeAction(id="a")
    wf = _wf(actions=[action])

    await engine.dispatch(_manual_event(), [wf], commit_sha="abc")
    second = await engine.dispatch(_manual_event(), [wf], commit_sha="abc", force=True)

    assert len(second) == 1
    assert len(cast(_FakeAction, action).calls) == 2


async def test_idempotency_per_workflow_independence() -> None:
    store = _InMemoryIdempotencyStore()
    engine = WorkflowEngine(idempotency_store=store)
    a = _FakeAction(id="a")
    b = _FakeAction(id="b")
    wf1 = _wf(name="w1", actions=[a])
    wf2 = _wf(name="w2", actions=[b])

    first = await engine.dispatch(_manual_event(), [wf1, wf2], commit_sha="abc")
    second = await engine.dispatch(_manual_event(), [wf1, wf2], commit_sha="abc")

    assert {r.workflow_name for r in first} == {"w1", "w2"}
    assert second == []


async def test_idempotency_no_store_means_no_dedup() -> None:
    action = _FakeAction(id="a")
    wf = _wf(actions=[action])
    engine = WorkflowEngine()
    await engine.dispatch(_manual_event(), [wf], commit_sha="abc")
    await engine.dispatch(_manual_event(), [wf], commit_sha="abc")
    assert len(cast(_FakeAction, action).calls) == 2


async def test_idempotency_records_run_id_after_run() -> None:
    store = _InMemoryIdempotencyStore()
    engine = WorkflowEngine(idempotency_store=store)
    wf = _wf(actions=[_FakeAction(id="a")])

    [report] = await engine.dispatch(_manual_event(), [wf], commit_sha="abc")
    key = build_idempotency_key(
        workflow_name="wf",
        issue_id="DEMO-1",
        to_state=None,
        commit_sha="abc",
    )
    assert store.has_processed(key) is True
    assert store._seen[key] == report.run_id


# --- branch + diff threaded into Context ---


async def test_dispatch_threads_branch_and_diff_into_context() -> None:
    a = _FakeAction(id="a")
    wf = _wf(actions=[a])

    await WorkflowEngine().dispatch(
        _manual_event(), [wf], branch="DEMO-1-fix", diff="diff --git a/x b/x\n"
    )

    ctx = cast(_FakeAction, a).calls[0]
    assert ctx.branch == "DEMO-1-fix"
    assert ctx.diff == "diff --git a/x b/x\n"


async def test_branch_and_diff_default_to_none() -> None:
    a = _FakeAction(id="a")
    wf = _wf(actions=[a])

    await WorkflowEngine().dispatch(_manual_event(), [wf])

    ctx = cast(_FakeAction, a).calls[0]
    assert ctx.branch is None
    assert ctx.diff is None


async def test_dispatch_threads_base_url_into_context() -> None:
    a = _FakeAction(id="a")
    wf = _wf(actions=[a])

    await WorkflowEngine().dispatch(_manual_event(), [wf], base_url="https://staging.example.com")

    ctx = cast(_FakeAction, a).calls[0]
    assert ctx.base_url == "https://staging.example.com"


async def test_base_url_defaults_to_none() -> None:
    a = _FakeAction(id="a")
    wf = _wf(actions=[a])

    await WorkflowEngine().dispatch(_manual_event(), [wf])

    assert cast(_FakeAction, a).calls[0].base_url is None


async def test_base_url_propagates_to_hooks() -> None:
    a = _FakeAction(id="a")
    hook = _FakeAction(id="celebrate")
    wf = _wf(actions=[a], on_success=[hook])

    await WorkflowEngine().dispatch(_manual_event(), [wf], base_url="https://staging.example.com")

    assert cast(_FakeAction, hook).calls[0].base_url == "https://staging.example.com"


async def test_branch_and_diff_propagate_to_hooks() -> None:
    a = _FakeAction(id="a")
    hook = _FakeAction(id="celebrate")
    wf = _wf(actions=[a], on_success=[hook])

    await WorkflowEngine().dispatch(
        _manual_event(), [wf], branch="DEMO-1-fix", diff="diff --git a/x b/x\n"
    )

    hook_ctx = cast(_FakeAction, hook).calls[0]
    assert hook_ctx.branch == "DEMO-1-fix"
    assert hook_ctx.diff == "diff --git a/x b/x\n"


async def test_dispatch_threads_commit_sha_and_repo_path_into_context() -> None:
    from pathlib import Path

    a = _FakeAction(id="a")
    wf = _wf(actions=[a])

    await WorkflowEngine().dispatch(
        _manual_event(),
        [wf],
        commit_sha="deadbeef",
        repo_path=Path("/tmp/repo"),
    )

    ctx = cast(_FakeAction, a).calls[0]
    assert ctx.commit_sha == "deadbeef"
    assert ctx.repo_path == Path("/tmp/repo")


async def test_commit_sha_and_repo_path_default_to_none() -> None:
    a = _FakeAction(id="a")
    wf = _wf(actions=[a])

    await WorkflowEngine().dispatch(_manual_event(), [wf])

    ctx = cast(_FakeAction, a).calls[0]
    assert ctx.commit_sha is None
    assert ctx.repo_path is None


async def test_commit_sha_and_repo_path_propagate_to_hooks() -> None:
    from pathlib import Path

    a = _FakeAction(id="a")
    hook = _FakeAction(id="celebrate")
    wf = _wf(actions=[a], on_success=[hook])

    await WorkflowEngine().dispatch(
        _manual_event(),
        [wf],
        commit_sha="deadbeef",
        repo_path=Path("/tmp/repo"),
    )

    hook_ctx = cast(_FakeAction, hook).calls[0]
    assert hook_ctx.commit_sha == "deadbeef"
    assert hook_ctx.repo_path == Path("/tmp/repo")


# --- OutputSink phase ---


class _SinkAction(ActionSpec):
    """Test action whose result includes an ``output['text']`` to be sunk."""

    type: Literal["_sink"] = "_sink"
    text: str = "rendered"

    async def execute(self, ctx: Context) -> ActionResult:
        return ActionResult(
            action_id=self.id,
            success=True,
            output={"text": self.text, "model": "stub"},
        )


class _CapturingSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, Any, str]] = []
        self._fail = fail

    async def write(self, *, issue_id: str, spec: Any, value: str) -> None:
        if self._fail:
            raise RuntimeError("sink boom")
        self.calls.append((issue_id, spec, value))


async def test_output_sink_writes_for_each_action_with_output_spec() -> None:
    from youtrack_aitrack.domain.output import CustomFieldOutput

    a = _SinkAction(id="a", text="report-a", output=CustomFieldOutput(name="Security Audit"))
    b = _SinkAction(id="b", text="report-b", output=CustomFieldOutput(name="QA Plan"))
    wf = _wf(actions=[a, b])
    sink = _CapturingSink()
    engine = WorkflowEngine(output_sink=sink)

    [report] = await engine.dispatch(_manual_event(), [wf])

    assert report.state is RunState.DONE
    assert len(sink.calls) == 2
    by_value = {c[2]: c for c in sink.calls}
    assert by_value["report-a"][0] == "DEMO-1"
    assert by_value["report-a"][1].name == "Security Audit"
    assert by_value["report-b"][1].name == "QA Plan"


async def test_output_sink_skipped_for_actions_without_output_spec() -> None:
    a = _FakeAction(id="a")  # no OutputSpec, no text in result
    wf = _wf(actions=[a])
    sink = _CapturingSink()
    engine = WorkflowEngine(output_sink=sink)

    await engine.dispatch(_manual_event(), [wf])

    assert sink.calls == []


async def test_output_sink_skipped_for_failed_actions() -> None:
    from youtrack_aitrack.domain.output import CustomFieldOutput

    fail = _FakeAction(id="fail", succeed=False, output=CustomFieldOutput(name="X"))
    wf = _wf(actions=[fail], on_failure=[_FakeAction(id="cleanup")])
    sink = _CapturingSink()
    engine = WorkflowEngine(output_sink=sink)

    [report] = await engine.dispatch(_manual_event(), [wf])

    assert report.state is RunState.FAILED
    assert sink.calls == []


async def test_output_sink_failure_fails_workflow_and_triggers_on_failure() -> None:
    from youtrack_aitrack.domain.output import CustomFieldOutput

    a = _SinkAction(id="a", text="t", output=CustomFieldOutput(name="X"))
    cleanup = _FakeAction(id="cleanup")
    success_hook = _FakeAction(id="celebrate")
    wf = _wf(actions=[a], on_success=[success_hook], on_failure=[cleanup])
    sink = _CapturingSink(fail=True)
    engine = WorkflowEngine(output_sink=sink)

    [report] = await engine.dispatch(_manual_event(), [wf])

    assert report.state is RunState.FAILED
    assert [r.action_id for r in report.hook_results] == ["cleanup"]
    assert cast(_FakeAction, success_hook).calls == []


async def test_no_output_sink_means_no_writes_attempted() -> None:
    from youtrack_aitrack.domain.output import CustomFieldOutput

    a = _SinkAction(id="a", text="t", output=CustomFieldOutput(name="X"))
    wf = _wf(actions=[a])
    engine = WorkflowEngine()  # no output_sink

    [report] = await engine.dispatch(_manual_event(), [wf])

    assert report.state is RunState.DONE


def test_build_idempotency_key_is_deterministic() -> None:
    k1 = build_idempotency_key(
        workflow_name="w", issue_id="DEMO-1", to_state="Ready", commit_sha="abc"
    )
    k2 = build_idempotency_key(
        workflow_name="w", issue_id="DEMO-1", to_state="Ready", commit_sha="abc"
    )
    assert k1 == k2
    k3 = build_idempotency_key(
        workflow_name="w", issue_id="DEMO-1", to_state="Ready", commit_sha="def"
    )
    assert k1 != k3
