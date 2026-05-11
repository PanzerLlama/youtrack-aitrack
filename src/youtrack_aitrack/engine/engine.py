"""WorkflowEngine — match triggers to events and execute action graphs."""

from __future__ import annotations

import asyncio
from typing import cast

from youtrack_aitrack.domain.action import Action, ActionSpec
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.run import ActionResult, RunReport, RunState
from youtrack_aitrack.domain.trigger import Trigger
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.engine.idempotency import IdempotencyStore, build_idempotency_key


class WorkflowEngine:
    def __init__(self, *, idempotency_store: IdempotencyStore | None = None) -> None:
        self._idempotency = idempotency_store

    async def dispatch(
        self,
        event: IssueEvent,
        workflows: list[Workflow],
        *,
        unavailable_inputs: set[str] | None = None,
        commit_sha: str | None = None,
        force: bool = False,
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
                *(self.run(w, event, unavailable_inputs=unavailable_inputs) for w, _ in scheduled)
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
    ) -> RunReport:
        outputs: dict[str, ActionResult] = {}
        failed = await _execute_graph(workflow.actions, event, outputs, unavailable_inputs or set())
        hook_specs = workflow.on_failure if failed else workflow.on_success
        hook_results = await _execute_hooks(hook_specs, event, outputs)
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
) -> bool:
    by_id = {a.id: a for a in specs}
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
                    action_id=aid, success=True, skipped=True, skip_reason=skip
                )
                remaining.discard(aid)
            else:
                to_run.append(aid)
        if not to_run:
            continue
        ctx = Context(issue=event, action_outputs=dict(outputs))
        results = await asyncio.gather(
            *(_run_one(by_id[aid], ctx) for aid in to_run),
            return_exceptions=True,
        )
        for aid, res in zip(to_run, results, strict=True):
            outputs[aid] = _coerce_result(aid, res)
            remaining.discard(aid)
            if not outputs[aid].success and not outputs[aid].skipped:
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
) -> list[ActionResult]:
    if not specs:
        return []
    ctx = Context(issue=event, action_outputs=dict(outputs))
    results = await asyncio.gather(
        *(_run_one(a, ctx) for a in specs),
        return_exceptions=True,
    )
    return [_coerce_result(a.id, r) for a, r in zip(specs, results, strict=True)]


async def _run_one(spec: ActionSpec, ctx: Context) -> ActionResult:
    action = cast(Action, spec)
    return await action.execute(ctx)


def _coerce_result(action_id: str, res: ActionResult | BaseException) -> ActionResult:
    if isinstance(res, BaseException):
        return ActionResult(action_id=action_id, success=False, error=str(res))
    return res
