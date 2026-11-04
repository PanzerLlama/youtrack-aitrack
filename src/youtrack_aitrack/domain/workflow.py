"""Workflow — top-level definition of a triggered automation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.trigger import TriggerSpec


class Workflow(BaseModel):
    name: str
    description: str | None = None
    trigger: TriggerSpec
    actions: list[ActionSpec]
    on_success: list[ActionSpec] = Field(default_factory=list)
    on_failure: list[ActionSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _check_action_ids_unique(self) -> Self:
        all_specs = [*self.actions, *self.on_success, *self.on_failure]
        ids = [a.id for a in all_specs]
        if len(ids) != len(set(ids)):
            raise ValueError("Action ids must be unique within a workflow")
        return self

    @model_validator(mode="after")
    def _check_depends_on_resolves(self) -> Self:
        action_ids = {a.id for a in self.actions}
        for a in self.actions:
            for dep in a.depends_on:
                if dep not in action_ids:
                    raise ValueError(f"Action {a.id!r} depends on unknown action {dep!r}")
                if dep == a.id:
                    raise ValueError(f"Action {a.id!r} depends on itself")
        for group_name, group in (
            ("on_success", self.on_success),
            ("on_failure", self.on_failure),
        ):
            for a in group:
                if a.depends_on:
                    raise ValueError(f"Action {a.id!r} in {group_name} cannot declare depends_on")
        return self


def select_actions(workflow: Workflow, action_ids: Iterable[str]) -> Workflow:
    """Restrict *workflow* to *action_ids* plus their transitive ``depends_on`` closure.

    Dependencies are re-run rather than read from a past run so downstream
    actions see fresh upstream output. Workflow-level hooks are dropped: a
    partial run must not flip ``on_success`` / ``on_failure`` fields for the
    whole workflow. Unknown ids raise ``ValueError`` listing the valid ones.
    """
    by_id = {a.id: a for a in workflow.actions}
    wanted = set(action_ids)
    unknown = sorted(wanted - by_id.keys())
    if unknown:
        raise ValueError(
            f"workflow {workflow.name!r} has no action(s) {unknown}; "
            f"available: {[a.id for a in workflow.actions]}"
        )
    selected: set[str] = set()
    stack = list(wanted)
    while stack:
        aid = stack.pop()
        if aid in selected:
            continue
        selected.add(aid)
        stack.extend(by_id[aid].depends_on)
    return workflow.model_copy(
        update={
            "actions": [a for a in workflow.actions if a.id in selected],
            "on_success": [],
            "on_failure": [],
        }
    )
