"""WorkflowEngine — match triggers to events and execute action graphs."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import cast

from youtrack_aitrack.domain.action import Action, ActionSpec
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.output import OutputSink
from youtrack_aitrack.domain.progress import (
    ActionOutcome,
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
)
from youtrack_aitrack.domain.run import ActionResult, RunReport, RunState
from youtrack_aitrack.domain.trigger import Trigger
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.engine.idempotency import IdempotencyStore, build_idempotency_key


class WorkflowEngine:
    def __init__(
        self,
        *,
        idempotency_store: IdempotencyStore | None = None,
        output_sink: OutputSink | None = None,
    ) -> None:
        self._idempotency = idempotency_store
        self._output_sink = output_sink

    async def dispatch(
        self,
        event: IssueEvent,
        workflows: list[Workflow],
        *,
        unavailable_inputs: set[str] | None = None,
        commit_sha: str | None = None,
        branch: str | None = None,
        diff: str | None = None,
        base_url: str | None = None,
        repo_path: Path | None = None,
        force: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> list[RunReport]:
        matched = [w for w in workflows if _trigger_matches(w, event)]
        if not matched:
            return []
        scheduled = [
            (w, self._key_for(w, event, commit_sha))
            for w in matched
            if force or not self._already_processed(w, event, commit_sha)
        ]
        if not scheduled:
            return []
        reports = list(
            await asyncio.gather(
                *(
                    self.run(
                        w,
                        event,
                        unavailable_inputs=unavailable_inputs,
                        branch=branch,
                        diff=diff,
                        base_url=base_url,
                        commit_sha=commit_sha,
                        repo_path=repo_path,
                        on_progress=on_progress,
                    )
                    for w, _ in scheduled
                )
            )
        )
        self._record(scheduled, reports)
        return reports

    def _key_for(self, workflow: Workflow, event: IssueEvent, commit_sha: str | None) -> str:
        return build_idempotency_key(
            workflow_name=workflow.name,
            issue_id=event.issue_id,
            to_state=event.to_state,
            commit_sha=commit_sha,
        )

    def _already_processed(
        self, workflow: Workflow, event: IssueEvent, commit_sha: str | None
    ) -> bool:
        if self._idempotency is None:
            return False
        return self._idempotency.has_processed(self._key_for(workflow, event, commit_sha))

    def _record(self, scheduled: list[tuple[Workflow, str]], reports: list[RunReport]) -> None:
        if self._idempotency is None:
            return
        for (_, key), report in zip(scheduled, reports, strict=True):
            self._idempotency.mark_processed(key, report.run_id)

    async def run(
        self,
        workflow: Workflow,
        event: IssueEvent,
        *,
        unavailable_inputs: set[str] | None = None,
        branch: str | None = None,
        diff: str | None = None,
        base_url: str | None = None,
        commit_sha: str | None = None,
        repo_path: Path | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> RunReport:
        outputs: dict[str, ActionResult] = {}
        failed = await _execute_graph(
            workflow.actions,
            event,
            outputs,
            unavailable_inputs or set(),
            workflow_name=workflow.name,
            branch=branch,
            diff=diff,
            base_url=base_url,
            commit_sha=commit_sha,
            repo_path=repo_path,
            on_progress=on_progress,
        )
        output_error: str | None = None
        if not failed and self._output_sink is not None:
            output_error = await _write_outputs(workflow.actions, outputs, event, self._output_sink)
            if output_error is not None:
                failed = True
        hook_specs = workflow.on_failure if failed else workflow.on_success
        hook_results = await _execute_hooks(
            hook_specs,
            event,
            outputs,
            workflow_name=workflow.name,
            branch=branch,
            diff=diff,
            base_url=base_url,
            commit_sha=commit_sha,
            repo_path=repo_path,
            on_progress=on_progress,
        )
        return RunReport(
            workflow_name=workflow.name,
            state=RunState.FAILED if failed else RunState.DONE,
            action_results=list(outputs.values()),
            hook_results=hook_results,
        )


def _trigger_matches(workflow: Workflow, event: IssueEvent) -> bool:
    return cast(Trigger, workflow.trigger).matches(event)


async def _execute_graph(
    specs: list[ActionSpec],
    event: IssueEvent,
    outputs: dict[str, ActionResult],
    unavailable_inputs: set[str],
    *,
    workflow_name: str,
    branch: str | None,
    diff: str | None,
    base_url: str | None,
    commit_sha: str | None,
    repo_path: Path | None,
    on_progress: ProgressCallback | None,
) -> bool:
    by_id = {a.id: a for a in specs}
    for spec in specs:
        _emit(on_progress, workflow_name, spec.id, "queued")
    remaining = set(by_id)
    failed = False
    while remaining and not failed:
        ready = sorted(
            aid for aid in remaining if all(dep in outputs for dep in by_id[aid].depends_on)
        )
        if not ready:
            break
        to_run: list[str] = []
        for aid in ready:
            skip = _skip_reason(by_id[aid], outputs, unavailable_inputs)
            if skip is not None:
                outputs[aid] = ActionResult(
                    action_id=aid, success=True, skipped=True, skip_reason=skip, duration_ms=0
                )
                _emit(on_progress, workflow_name, aid, "finished", outcome="skipped", duration_ms=0)
                remaining.discard(aid)
            else:
                to_run.append(aid)
        if not to_run:
            continue
        ctx = Context(
            issue=event,
            branch=branch,
            diff=diff,
            base_url=base_url,
            commit_sha=commit_sha,
            repo_path=repo_path,
            action_outputs=dict(outputs),
        )
        results = await asyncio.gather(
            *(
                _run_timed(by_id[aid], ctx, workflow_name=workflow_name, on_progress=on_progress)
                for aid in to_run
            )
        )
        for aid, res in zip(to_run, results, strict=True):
            outputs[aid] = res
            remaining.discard(aid)
            if not res.success and not res.skipped:
                failed = True
    return failed


def _skip_reason(
    spec: ActionSpec,
    outputs: dict[str, ActionResult],
    unavailable_inputs: set[str],
) -> str | None:
    missing = [i for i in spec.inputs if i in unavailable_inputs]
    if missing:
        return f"missing inputs: {sorted(missing)}"
    skipped_parents = [d for d in spec.depends_on if outputs[d].skipped]
    if skipped_parents:
        return f"depends_on skipped: {sorted(skipped_parents)}"
    return None


async def _execute_hooks(
    specs: list[ActionSpec],
    event: IssueEvent,
    outputs: dict[str, ActionResult],
    *,
    workflow_name: str,
    branch: str | None,
    diff: str | None,
    base_url: str | None,
    commit_sha: str | None,
    repo_path: Path | None,
    on_progress: ProgressCallback | None,
) -> list[ActionResult]:
    if not specs:
        return []
    for spec in specs:
        _emit(on_progress, workflow_name, spec.id, "queued", is_hook=True)
    ctx = Context(
        issue=event,
        branch=branch,
        diff=diff,
        base_url=base_url,
        commit_sha=commit_sha,
        repo_path=repo_path,
        action_outputs=dict(outputs),
    )
    return list(
        await asyncio.gather(
            *(
                _run_timed(
                    a, ctx, workflow_name=workflow_name, is_hook=True, on_progress=on_progress
                )
                for a in specs
            )
        )
    )


async def _run_timed(
    spec: ActionSpec,
    ctx: Context,
    *,
    workflow_name: str,
    is_hook: bool = False,
    on_progress: ProgressCallback | None,
) -> ActionResult:
    """Time one action, stamp ``duration_ms``, and emit start/finish progress.

    Any exception escaping ``execute`` is coerced to a failed ActionResult,
    preserving the previous ``gather(return_exceptions=True)`` behaviour while
    keeping cancellation propagating.
    """
    _emit(on_progress, workflow_name, spec.id, "started", is_hook=is_hook)
    started = time.monotonic()
    try:
        result = await cast(Action, spec).execute(ctx)
    except Exception as exc:  # surface as a failed action, never crash the run
        result = ActionResult(action_id=spec.id, success=False, error=str(exc))
    duration_ms = int((time.monotonic() - started) * 1000)
    result = result.model_copy(update={"duration_ms": duration_ms})
    _emit(
        on_progress,
        workflow_name,
        spec.id,
        "finished",
        is_hook=is_hook,
        outcome=_outcome(result),
        duration_ms=duration_ms,
    )
    return result


def _outcome(result: ActionResult) -> ActionOutcome:
    if result.skipped:
        return "skipped"
    return "ok" if result.success else "fail"


def _emit(
    on_progress: ProgressCallback | None,
    workflow_name: str,
    action_id: str,
    phase: ProgressPhase,
    *,
    is_hook: bool = False,
    outcome: ActionOutcome | None = None,
    duration_ms: int | None = None,
) -> None:
    if on_progress is None:
        return
    on_progress(
        ProgressEvent(
            workflow_name=workflow_name,
            action_id=action_id,
            phase=phase,
            is_hook=is_hook,
            outcome=outcome,
            duration_ms=duration_ms,
        )
    )


async def _write_outputs(
    specs: list[ActionSpec],
    outputs: dict[str, ActionResult],
    event: IssueEvent,
    sink: OutputSink,
) -> str | None:
    """Persist each action's ``output['text']`` to its declared OutputSpec sink.

    Returns None on success, or an error string on the first failure (rest are skipped).
    """
    for spec in specs:
        if spec.output is None:
            continue
        result = outputs.get(spec.id)
        if result is None or not result.success or result.skipped:
            continue
        value = (result.output or {}).get("text")
        if not isinstance(value, str):
            continue
        try:
            await sink.write(issue_id=event.issue_id, spec=spec.output, value=value)
        except Exception as exc:
            return f"output sink failed for action {spec.id!r}: {exc}"
    return None
