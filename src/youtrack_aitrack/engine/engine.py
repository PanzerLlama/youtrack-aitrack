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


class WorkflowEngine:
    async def dispatch(
        self,
        event: IssueEvent,
        workflows: list[Workflow],
    ) -> list[RunReport]:
        matched = [w for w in workflows if _trigger_matches(w, event)]
        if not matched:
            return []
        return list(await asyncio.gather(*(self.run(w, event) for w in matched)))

    async def run(self, workflow: Workflow, event: IssueEvent) -> RunReport:
        outputs: dict[str, ActionResult] = {}
        failed = await _execute_graph(workflow.actions, event, outputs)
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
        ctx = Context(issue=event, action_outputs=dict(outputs))
        results = await asyncio.gather(
            *(_run_one(by_id[aid], ctx) for aid in ready),
            return_exceptions=True,
        )
        for aid, res in zip(ready, results, strict=True):
            outputs[aid] = _coerce_result(aid, res)
            remaining.discard(aid)
            if not outputs[aid].success:
                failed = True
    return failed


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
