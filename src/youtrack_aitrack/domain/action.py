"""ActionSpec data shape and Action behaviour Protocol."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.output import OutputSpec
from youtrack_aitrack.domain.run import ActionResult


class ActionSpec(BaseModel):
    id: str
    type: str
    depends_on: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    output: OutputSpec | None = None

    # extra="allow" keeps type-specific fields until registry promotes to a concrete subclass
    model_config = ConfigDict(frozen=True, extra="allow")


class Action(Protocol):
    id: str

    async def execute(self, ctx: Context) -> ActionResult: ...
