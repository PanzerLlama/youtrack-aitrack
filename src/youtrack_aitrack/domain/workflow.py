"""Workflow — top-level definition of a triggered automation."""

from __future__ import annotations

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
