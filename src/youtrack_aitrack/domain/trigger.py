"""TriggerSpec data shape and Trigger behaviour Protocol."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from youtrack_aitrack.domain.event import IssueEvent


class TriggerSpec(BaseModel):
    type: str

    # extra="allow" keeps type-specific fields until registry promotes to a concrete subclass
    model_config = ConfigDict(frozen=True, extra="allow")


class Trigger(Protocol):
    def matches(self, event: IssueEvent) -> bool: ...
